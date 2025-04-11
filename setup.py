from setuptools import setup

setup(
    name='p2p-ec530',
    version='0.1.0',
    py_modules=['p2p'],  
    install_requires=['plyer'],  
    entry_points={
        'console_scripts': [
            'p2p-cli=p2p:main',  
        ],
    },
    author='Akhil Bongu',
    author_email='akhil.ssj2@gmail.com',
    description='A P2P communication project for EC530',
    long_description=open('README.md').read(),
    long_description_content_type='text/markdown',
    classifiers=[
        'Programming Language :: Python :: 3',
        'License :: OSI Approved :: MIT License',
    ],
    python_requires='>=3.7',
)
