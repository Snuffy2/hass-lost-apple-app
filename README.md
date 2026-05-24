# Repository Coverage

[Full report](https://htmlpreview.github.io/?https://github.com/Snuffy2/hass-lost-apple-app/blob/python-coverage-comment-action-data/htmlcov/index.html)

| Name                                       |    Stmts |     Miss |   Branch |   BrPart |   Cover |   Missing |
|------------------------------------------- | -------: | -------: | -------: | -------: | ------: | --------: |
| app/src/lost\_apple\_app/\_\_init\_\_.py   |        0 |        0 |        0 |        0 |    100% |           |
| app/src/lost\_apple\_app/\_\_main\_\_.py   |       59 |        5 |       10 |        4 |     87% |53, 57, 63-\>65, 70, 103, 112 |
| app/src/lost\_apple\_app/api.py            |       43 |        3 |       14 |        1 |     89% |     70-73 |
| app/src/lost\_apple\_app/auth.py           |       11 |        0 |        2 |        0 |    100% |           |
| app/src/lost\_apple\_app/config.py         |       41 |        8 |       12 |        3 |     79% |19-21, 23-24, 32-33, 61 |
| app/src/lost\_apple\_app/const.py          |        3 |        0 |        0 |        0 |    100% |           |
| app/src/lost\_apple\_app/findmy\_client.py |      114 |       46 |       38 |        3 |     51% |165-170, 185, 191, 200-\>202, 210-213, 218-242, 247-255, 260-264, 269-278 |
| app/src/lost\_apple\_app/models.py         |       23 |        0 |        0 |        0 |    100% |           |
| app/src/lost\_apple\_app/polling.py        |       52 |        4 |        8 |        2 |     90% |72, 79, 103-104 |
| app/src/lost\_apple\_app/storage.py        |       97 |        2 |       16 |        2 |     96% |   86, 104 |
| app/src/lost\_apple\_app/web.py            |      134 |       31 |       24 |        7 |     75% |80-81, 102, 108, 121-128, 136, 414-416, 439-447, 460, 477, 482-485, 492-494, 518-519 |
| **TOTAL**                                  |  **577** |   **99** |  **124** |   **22** | **78%** |           |


## Setup coverage badge

Below are examples of the badges you can use in your main branch `README` file.

### Direct image

[![Coverage badge](https://raw.githubusercontent.com/Snuffy2/hass-lost-apple-app/python-coverage-comment-action-data/badge.svg)](https://htmlpreview.github.io/?https://github.com/Snuffy2/hass-lost-apple-app/blob/python-coverage-comment-action-data/htmlcov/index.html)

This is the one to use if your repository is private or if you don't want to customize anything.

### [Shields.io](https://shields.io) Json Endpoint

[![Coverage badge](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/Snuffy2/hass-lost-apple-app/python-coverage-comment-action-data/endpoint.json)](https://htmlpreview.github.io/?https://github.com/Snuffy2/hass-lost-apple-app/blob/python-coverage-comment-action-data/htmlcov/index.html)

Using this one will allow you to [customize](https://shields.io/endpoint) the look of your badge.
It won't work with private repositories. It won't be refreshed more than once per five minutes.

### [Shields.io](https://shields.io) Dynamic Badge

[![Coverage badge](https://img.shields.io/badge/dynamic/json?color=brightgreen&label=coverage&query=%24.message&url=https%3A%2F%2Fraw.githubusercontent.com%2FSnuffy2%2Fhass-lost-apple-app%2Fpython-coverage-comment-action-data%2Fendpoint.json)](https://htmlpreview.github.io/?https://github.com/Snuffy2/hass-lost-apple-app/blob/python-coverage-comment-action-data/htmlcov/index.html)

This one will always be the same color. It won't work for private repos. I'm not even sure why we included it.

## What is that?

This branch is part of the
[python-coverage-comment-action](https://github.com/marketplace/actions/python-coverage-comment)
GitHub Action. All the files in this branch are automatically generated and may be
overwritten at any moment.