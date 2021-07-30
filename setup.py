from setuptools import setup, find_packages
setup(
    name="fotocop",
    version="1.0",
    packages=find_packages(),
    entry_points={
        'console_scripts': [
            'dcfsBuilder = dcfs_builder.__main__.py:run_main',
        ],
    }
)
