from setuptools import setup, find_packages


with open("README.md", "r") as fh:
    long_description = fh.read()

reqs = ['numpy>=1.14', 'scikit-image>=0.15', 'scipy>=1.1', 'pandas>=0.25']

setup(
    name='creativeflow',
    version='0.0.1',
    author='Maria Shugrina',
    author_email='creative.flow.dataset@gmail.com',
    description='Package accompanying Creative Flow+ Dataset, CVPR 2019.',
    long_description=long_description,
    long_description_content_type='text/markdown',
    url='https://github.com/creativefloworg/creativeflow',
    py_modules=['creativeflow.blender.flow_util', 'creativeflow.blender.io_util', 'creativeflow.blender.dataset_util'],
    python_requires='>=3.0',
    install_requires=reqs,
    test_suite='creativeflow.tests',
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent"
    ],
)
