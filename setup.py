from setuptools import setup, find_packages

setup(
    name="hipforge-cli",
    version="0.1.0",
    packages=find_packages(),
    py_modules=["cli.hipforge"],
    install_requires=[
        "requests",
        "websockets",
    ],
    entry_points={
        "console_scripts": [
            "hipforge=cli.hipforge:main",
        ],
    },
)
