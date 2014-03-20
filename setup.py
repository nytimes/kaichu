from setuptools import setup, find_packages

setup(name='kaichu',
      version='0.0.0',
      packages=find_packages(),
      install_requires=['jira-python',
                        'sneeze'],
      entry_points={'nose.plugins.sneeze.plugins.add_models' : ['kaichu_models = kaichu.models:add_models'],
                    'nose.plugins.sneeze.plugins.add_options' : ['kaichu_options = kaichu.interface:add_options'],
                    'nose.plugins.sneeze.plugins.managers' : ['kaichu_manager = kaichu.interface:KaichuManager']})