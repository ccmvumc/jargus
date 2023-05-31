from setuptools import setup, find_packages

setup(
    name="jargus",
    version="1.0.0",
    author="Brian D. Boyd",
    author_email="brian.d.boyd@vumc.org",
    description="A Python package for managing reports in REDCap",
    long_description=open("README.md").read(),
    long_description_content_type="text/x-md",
    url="https://github.com/bud42/jargus",
    packages=find_packages(),
    classifiers=[
        "Development Status :: 3 - Alpha",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.10",
    ],
    install_requires=[
        "pandas",
        "pycap",
        "click",
        "sphinx",
        "pydot",
        "plotly",
    ],
    entry_points={"console_scripts": ["jargus = jargus.cli:cli"]},
)
