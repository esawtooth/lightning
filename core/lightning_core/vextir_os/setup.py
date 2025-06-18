import os

from setuptools import find_packages, setup


# Read README if available
def read_readme():
    path = os.path.join(os.path.dirname(__file__), "README.md")
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    return "Vextir OS core package"


setup(
    name="vextir-os",
    version="0.1.0",
    description="Core implementation of the Vextir AI Operating System",
    long_description=read_readme(),
    long_description_content_type="text/markdown",
    author="Vextir OS Team",
    packages=find_packages(),
    include_package_data=True,
    entry_points={
        "console_scripts": [
            "vextir-os-processor=vextir_os.cli:main",
        ]
    },
    python_requires=">=3.8",
)
