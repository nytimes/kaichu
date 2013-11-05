from jira.client import JIRA
import requests
from requests_oauthlib import OAuth1
from oauthlib.oauth1 import SIGNATURE_RSA
import json


class Client(JIRA):
    
    def __init__(self, pocket_change_host, jira_host, app_key,
                 username=None, password=None, token=None, oauth_data=None,
                 options=None):
        
        if options is None:
            options = {}
        
        self._options = JIRA.DEFAULT_OPTIONS
        self._options.update(options)
        
        if jira_host:
            self._options['server'] = jira_host
        jira_host = self._options['server'] = self._options['server'].rstrip('/')
        
        self._try_magic()
        
        if oauth_data:
            self.rsa_key, self.resource_owner_key, self.resource_owner_secret = oauth_data
        else:
            params = {'app_key' : app_key,
                      'username' : username}
            if password:
                params['password'] = password
            if token:
                params['token'] = token
            auth_data_response = requests.get(pocket_change_host + '/rest/jira_auth_data',
                                              params=params)
            if 199 < auth_data_response.status_code < 300:
                auth_data = json.loads(auth_data_response.content)
                self.rsa_key = auth_data['rsa_key']
                self.resource_owner_key = auth_data['oauth_token']
                self.resource_owner_secret = auth_data['oauth_secret']
            else:
                raise ValueError('Pocket Change or Jira data incorrect.')
        self._session = requests.Session()
        self._session.verify = self._options['verify']
        self._session.auth = OAuth1(app_key,
                                    rsa_key=self.rsa_key,
                                    signature_method=SIGNATURE_RSA,
                                    resource_owner_key=self.resource_owner_key,
                                    resource_owner_secret=self.resource_owner_secret)