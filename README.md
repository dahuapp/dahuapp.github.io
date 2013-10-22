dahuapp.github.io
=================

Web page of the Dahu application.

# About

The Dahu web page is static and is generated by combining the
powerful Jinja2 template engine with Fabric automation tool.

# Requirement

For generating this web page you need the following installed on
your computer:

- bower (see http://bower.io/)
- scss (see http://sass-lang.com/)
- pip (see http://www.pip-installer.org/)

The building process requires some python dependencies that can be obtained by running:

    > pip install -r requirements.txt

# Convention

For the web page to be nicely designed we have to respect few convention.

## Images

Image size must respect the golden ratio.
A common size of image is: 800 x 500.

Please respect this ratio.


# Generate / Check / Publish

## Generate

For generating the web site you need to run

    > fab generate

## Publish

For publishing the web site you need to run

    > fab publish

**info** currently the publication is done on the devel-gh-pages branch.

## Serve

For watching the generated web site locally just run

    > fab serve

## Clean

For cleaning the project just run

    > fab clean