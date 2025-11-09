from setuptools import setup, find_packages

setup(
    name="fake_knx_pv",
    version='0.3.3',
    author="Eric",
    description="Simulation KNX PV pour données de production et consommation.",
    packages=find_packages(),
    include_package_data=True,
    install_requires=[
        "xknx",
        "pytz",
        "astral",
        "requests"
    ],
    python_requires='>=3.7',
)
