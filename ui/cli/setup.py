#!/usr/bin/env python3
"""
Setup script for Vextir CLI
"""

from setuptools import setup, find_packages
import os

# Read the README file
def read_readme():
    readme_path = os.path.join(os.path.dirname(__file__), 'README.md')
    if os.path.exists(readme_path):
        with open(readme_path, 'r', encoding='utf-8') as f:
            return f.read()
    return "Vextir OS Command Line Interface"

# Read requirements
def read_requirements():
    req_path = os.path.join(os.path.dirname(__file__), 'requirements.txt')
    requirements = []
    if os.path.exists(req_path):
        with open(req_path, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    requirements.append(line)
    return requirements

setup(
    name="vextir-cli",
    version="1.0.0",
    description="Command Line Interface for Vextir AI Operating System",
    long_description=read_readme(),
    long_description_content_type="text/markdown",
    author="Vextir OS Team",
    author_email="team@vextir.com",
    url="https://github.com/vextir/vextir-cli",
    packages=find_packages(),
    include_package_data=True,
    install_requires=read_requirements(),
    entry_points={
        'console_scripts': [
            'vextir=ui.cli.main:cli',
        ],
    },
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "Intended Audience :: System Administrators",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Topic :: Software Development :: Libraries :: Python Modules",
        "Topic :: System :: Systems Administration",
        "Topic :: Utilities",
    ],
    python_requires=">=3.8",
    keywords="vextir ai cli command-line interface automation",
    project_urls={
        "Bug Reports": "https://github.com/vextir/vextir-cli/issues",
        "Source": "https://github.com/vextir/vextir-cli",
        "Documentation": "https://docs.vextir.com/cli",
    },
)
