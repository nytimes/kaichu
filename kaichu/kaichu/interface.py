from collections import Counter
from kaichu.jira_lib import Client as JiraClient


def add_options(parser, env):
    
    parser.add_option('--kaichu-jira-host',
                      action='store',
                      default=env.get('kaichu_jira_host', ''),
                      dest='kaichu_jira_host',
                      help='Base URL of Jira instance.')
    parser.add_option('--kaichu-jira-project-key',
                      action='store',
                      default=env.get('kaichu_jira_project_key', ''),
                      dest='kaichu_jira_project_key',
                      help='Key of project for kaichu to report to.')
    parser.add_option('--rerun-from-jira-issue',
                      action='store',
                      default='',
                      dest='jira_issue_rerun',
                      help='Key or id of jira issue tracking a failure.')
    parser.add_option('--kaichu-jira-app-key',
                      action='store',
                      default=env.get('kaichu_jira_app_key'),
                      dest='kaichu_jira_app_key',
                      help='OAuth app key for jira.')
#    parser.add_option('--kaichu-ignore-previous-results',
#                      action='store_false',
#                      default=False,
#                      dest='kaichu_ignore_previous_results',
#                      help='Ignore previous test results (force all to run).')


class KaichuManager(object):
    
    @classmethod
    def enabled(cls, tissue, options, noseconfig):
        
        if (options.kaichu_jira_host
            and options.pocket_change_username
            and (options.pocket_change_password or options.pocket_change_token)
            and options.kaichu_jira_app_key
            and options.kaichu_jira_project_key):
            try:
                KaichuManager.jira = JiraClient(options.pocket_change_host,
                                                options.kaichu_jira_host,
                                                options.kaichu_jira_app_key,
                                                options.pocket_change_username,
                                                options.pocket_change_password,
                                                options.pocket_change_token)
            except ValueError:
                return False
            else:
                return True
        else:
            return False
    
    def __init__(self, tissue, options, noseconfig):
        
        # TODO: Fix this
        # Hacks to prevent requests from logging messages
        # (when we interact with Jira); these log messages
        # can lock up the message logger as they can come
        # in the midst of transitional states
        from logging import CRITICAL, getLogger
        getLogger('requests').setLevel(CRITICAL)
        getLogger('oauthlib').setLevel(CRITICAL)
        self.tissue = tissue
        if hasattr(KaichuManager, 'jira') and KaichuManager.jira:
            self.jira = KaichuManager.jira
        else:
            self.jira = JiraClient(options.pocket_change_host,
                                   options.kaichu_jira_host,
                                   options.kaichu_jira_app_key,
                                   options.pocket_change_username,
                                   options.pocket_change_password,
                                   options.pocket_change_token)
        self.jira_project_key = options.kaichu_jira_project_key
        self.test_cycle_issue = None
    
    def enter_test_cycle(self):
        
        with self.tissue.session_transaction():
            if not self.tissue.test_cycle.jira_issue:
                self.test_cycle_issue = self.jira.create_issue(project={'key' : self.jira_project_key},
                                                               summary=self.tissue.test_cycle.name,
                                                               description=self.tissue.test_cycle.description,
                                                               issuetype={'name' : 'Test Cycle'})
                self.tissue.test_cycle.jira_issue = self.tissue.db_models['TestCycleIssue'](issue_id=self.test_cycle_issue.id)
            else:
                self.test_cycle_issue = self.jira.issue(str(self.tissue.test_cycle.jira_issue.issue_id))
            if self.tissue.test_cycle.running_count == 1:
                available_transitions = {t['name'] : t['id'] for t in self.jira.transitions(self.test_cycle_issue)}
                try:
                    transition_id = available_transitions[u'Review']
                except KeyError:
                    pass
                else:
                    self.jira.transition_issue(self.test_cycle_issue, transition_id)
                    self.jira.add_comment(self.test_cycle_issue,
                                          ('Reviewing for automation rerun. (%d)'
                                           % self.tissue.execution_batch.id))
                    available_transitions = {t['name'] : t['id'] for t in self.jira.transitions(self.test_cycle_issue)}
                try:
                    transition_id = available_transitions['Begin']
                except KeyError:
                    transition_id = available_transitions[u'Rerun']
                self.jira.transition_issue(self.test_cycle_issue, transition_id)
                self.jira.add_comment(self.test_cycle_issue,
                                      'Starting execution. (%d)' % self.tissue.execution_batch.id)
            else:
                self.jira.add_comment(self.test_cycle_issue, 'Starting execution. (%d)' % self.tissue.execution_batch.id)
    
    def exit_test_cycle(self):
        
        if self.tissue.test_cycle.running_count == 0:
            transition_id = {t['name'] : t['id'] for t in
                             self.jira.transitions(self.test_cycle_issue)}[u'Complete Execution']
            self.jira.transition_issue(self.test_cycle_issue, transition_id)
            self.jira.add_comment(self.test_cycle_issue, ('All pending executions complete. (%d)'
                                                          % self.tissue.execution_batch.id))
        else:
            self.jira.add_comment(self.test_cycle_issue, ('Execution batch complete. (%d)'
                                                          % self.tissue.execution_batch.id))
    
    def _handle_not_pass(self, status, issue_type_name, message):
        
        with self.tissue.session_transaction() as session:
            CE = self.tissue.db_models['CaseExecution']
            CEI = self.tissue.db_models['CaseExecutionIssue']
            previous_cycle_executions = (session.query(CE).filter(CE.case==self.tissue.case_execution.case,
                                                                  CE.test_cycles.contains(self.tissue.test_cycle),
                                                                  CE.id!=self.tissue.case_execution.id)
                                         .all())
            if previous_cycle_executions:
                previous_issues = (session.query(CEI).filter(CEI.case_execution_id.in_([ce.id for ce in
                                                                                        previous_cycle_executions]))
                                   .all())
            else:
                previous_issues = ()
            if not previous_issues:
                summary = 'automation %s of %s' % (status.lower(), self.tissue.case_execution.description)
                description = self._build_result_blurb(status, message)
                if previous_cycle_executions:
                    result_counts = Counter(case_execution.result for case_execution in previous_cycle_executions)
                    description += ('\n\nPrevious results not logged in Jira for this case in this cycle.\n'
                                    + ('Pending: %d   Failed: %d   Skipped: %d   Passed: %d'
                                       % (result_counts['PENDING'], result_counts['FAIL'],
                                          result_counts['SKIP'], result_counts['PASS'])))
                issue = self.jira.create_issue(project={'key' : self.jira_project_key},
                                               summary=summary,
                                               description=description,
                                               issuetype={'name' : issue_type_name},
                                               parent={'id' : self.test_cycle_issue.id})
            else:
                issue = self.jira.issue(str(previous_issues[-1].issue_id))
                self.jira.add_comment(issue, self._build_result_blurb('rerun ' + status, message))
            self.tissue.case_execution.jira_issue = CEI(issue_id=int(issue.id))
    
    def _build_result_blurb(self, status, message):
        
        return (('AUTOMATION %s\n' % status.upper())
                + ('\n%s\n' % message)
                + '\nCase:\n'
                + self.tissue.case_execution.description + (' (%d)\n' % self.tissue.case_execution.id)
                + self.tissue.case_execution.case.label + (' (%d)\n' % self.tissue.case_execution.case.id)
                + '\nTest Cycle:\n'
                + self.tissue.test_cycle.name + (' (%d)\n' % self.tissue.test_cycle.id)
                + self.tissue.test_cycle.description + '\n'
                + '\nBatch:\n'
                + ('id %d\n' % self.tissue.execution_batch.id)
                + self.tissue.execution_batch.host)
    
    def handle_fail(self, message):
        
        self._handle_not_pass('failure', 'Test Failure', message)
    
    def handle_skip(self, message):
        
        self._handle_not_pass('skip', 'Test Failure', message)
    
    def handle_pass(self):
        
        with self.tissue.session_transaction() as session:
            CE = self.tissue.db_models['CaseExecution']
            CEI = self.tissue.db_models['CaseExecutionIssue']
            previous_cycle_executions = (session.query(CE).filter(CE.case==self.tissue.case_execution.case,
                                                                  CE.test_cycles.contains(self.tissue.test_cycle),
                                                                  CE.id!=self.tissue.case_execution.id)
                                         .all())
            if previous_cycle_executions:
                previous_issues = (session.query(CEI).filter(CEI.case_execution_id.in_([ce.id for ce in
                                                                                        previous_cycle_executions]))
                                   .all())
            else:
                previous_issues = ()
            if previous_issues:
                issue = self.jira.issue(str(previous_issues[0].issue_id))
                self.jira.add_comment(issue, self._build_result_blurb('rerun pass', ''))