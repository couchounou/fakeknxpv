from setuptools import setup, find_packages

setup(
    name="fake_knx_pv",
    version="0.1.0",
    author="VotreNom",
    description="Simulation KNX PV pour données de production et consommation.",
    packages=find_packages(),
    include_package_data=True,
    install_requires=[],
    python_requires='>=3.7',
)