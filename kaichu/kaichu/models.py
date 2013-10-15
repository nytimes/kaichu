from sqlalchemy import Column, Integer, ForeignKey, String, DateTime, Boolean
from sqlalchemy.orm import relationship, backref
from datetime import datetime


def add_models(Base):
    
    
    class TestCycleIssue(Base):
        
        __tablename__ = 'testCycleIssue'
        
        test_cycle_id = Column(Integer, ForeignKey('testCycle.id'), primary_key=True)
        test_cycle = relationship('TestCycle',
                                  backref=backref('jira_issue', uselist=False), uselist=False)
        issue_id = Column(Integer)
    
    
    class CaseExecutionIssue(Base):
        
        __tablename__ = 'testCaseExecutionIssue'
        
        case_execution_id = Column(Integer, ForeignKey('testCaseExecution.id'), primary_key=True)
        case_execution = relationship('CaseExecution',
                                      backref=backref('jira_issue', uselist=False), uselist=False)
        issue_id = Column(Integer)
    
    
    class UserJiraData(Base):
        
        __tablename__ = 'userJiraData'
        
        user_id = Column(Integer, ForeignKey('user.id'), primary_key=True)
        user = relationship('User', backref=backref('jira', uselist=False), uselist=False)
        name = Column(String(75))
        oauth_token = Column(String(36), nullable=True)
        oauth_secret = Column(String(36), nullable=True)
        expires = Column(DateTime, nullable=True)
        revoked = Column(Boolean)
        
        @property
        def expired(self):
            
            return bool(self.expires and datetime.now() > self.expires)
        
        @property
        def active(self):
            
            return not self.revoked and not self.expired
    
    
    return {'TestCycleIssue' : TestCycleIssue, 'CaseExecutionIssue' : CaseExecutionIssue,
            'UserJiraData' : UserJiraData}