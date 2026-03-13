from setuptools import setup, find_packages

setup(
    name="skillguard",
    version="1.0.0",
    description="SkillGuard — AI Skills Security Evaluator",
    packages=find_packages(),
    py_modules=["cli"],
    python_requires=">=3.10",
    install_requires=[],
    extras_require={
        "yaml": ["pyyaml"],
    },
    entry_points={
        "console_scripts": [
            "skillguard=cli:main",
        ],
    },
)
