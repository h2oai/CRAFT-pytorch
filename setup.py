from setuptools import setup, find_packages

# read version
about_info = {}
with open("version.txt", "r") as v:
    exec(v.read(), about_info)

with open("README.md", "r") as fh:
    long_description = fh.read()

setup(
    name="h2o_craft",
    version=about_info["version"],
    description="H2O.ai port of Pytorch implementation of CRAFT text detector",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://www.h2o.ai",
    author="H2O.ai",
    author_email="team@h2o.ai",
    license="MIT License",
    classifiers=[
        "Development Status :: 1 - Planning",
        "Environment :: Other Environment",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Topic :: Scientific/Engineering :: Artificial Intelligence",
        "Topic :: Scientific/Engineering :: Image Recognition",
    ],
    keywords="",
    packages=find_packages(),
    python_requires="~=3.6",
    install_requires=[
        "torch~=1.5.0",
        "torchvision~=0.6.0",
        "opencv-python~=4.2.0",
        "scikit-image~=0.17.2",
        "scipy~=1.4.0",
        "requests~=2.23.0",
        "pillow~=7.1.0",
    ],
    dependency_links=[],
    # package_data={},
    # data_files=[],
    # entry_points={},
)
