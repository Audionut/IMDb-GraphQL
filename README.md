# General Information
introspection.py is a utility to find all of the IMDb GraphQL API objects.

## Features
- Get everything related to the API
- Generate examples

## Installation
- `pip3 install -r requirements.txt`
    - You may need to use a venv

## Usage
- Help
    - `python 3 introspection.py --help`

- Run without arguments first to get the required data.
    - `python3 introspection.py`

- You can then use the existing data to generate example calls
    - `python3 introspection.py --example advancedNameSearch "Brad Pitt"`

# Atrributions

All metadata fetched from the following providers is to be used and creditted following their respective TOS.

## Internet Movie Database (IMDb)

<center><a href="https://imdb.com/"><img src="images/imdb.svg" alt="IMDb Logo" title="IMDb" height="60"/></a></center>


Metadata provided by IMDb. Please consider [adding missing information](https://help.imdb.com/article/contribution/contribution-information/adding-new-data/G6BXD2JFDCCETUF4).

This interface is provided free of charge and is not intended to be used for commercial and/or for profit projects. If you wish to use this implementation for that, you must comply with IMDb's terms for gaining access for that type. [Getting Commercial/Paid API Access](https://developer.imdb.com/documentation/api-documentation/getting-access/?ref_=up_next)