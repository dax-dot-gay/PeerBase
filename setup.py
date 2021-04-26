from setuptools import setup
with open("README.md", encoding='utf-8') as f:
    readme = f.read()

setup(
  name = 'peerbase',         # How you named your package folder (MyLib)
  packages = ['peerbase'],   # Chose the same as "name"
  version = '0.5',      # Start with a small number and increase it with every change you make
  license='MIT',        # Chose a license from here: https://help.github.com/articles/licensing-a-repository
  description = 'High-level p2p protocol allowing both local and remote p2p connections via UDP advertising and a TURN-like middleman server (or multiple)',   # Give a short description about your library
  long_description_content_type="text/markdown",
  long_description=readme,
  author = 'iTecX',                   # Type in your name
  author_email = 'matteovh@gmail.com',      # Type in your E-Mail
  url = 'https://github.com/iTecAI/PeerBase',   # Provide either the link to your github or to your website
  download_url = 'https://github.com/iTecAI/PeerBase/archive/refs/tags/0.5.tar.gz',    # I explain this later on
  keywords = ['p2p','peer-to-peer','http'],   # Keywords that define your package best
  install_requires=[            # I get to this in a second
          'cryptography',
          'requests',
          'fastapi',
          'uvicorn'
      ],
  classifiers=[
    'Development Status :: 3 - Alpha',      # Chose either "3 - Alpha", "4 - Beta" or "5 - Production/Stable" as the current state of your package
    'Intended Audience :: Developers',      # Define that your audience are developers
    'Topic :: Software Development :: Build Tools',
    'License :: OSI Approved :: MIT License',   # Again, pick a license
    'Programming Language :: Python :: 3.8',
    'Programming Language :: Python :: 3.9'
  ],
)