# azure-storage-upload-files
[![Build](https://github.com/RaaLabs/azure-storage-upload-files/actions/workflows/build.yml/badge.svg)](https://github.com/RaaLabs/azure-storage-upload-files/actions/workflows/build.yml)

GitHub action to upload files to multiple Azure storage accounts.

> **Warning**
> We are switching from Docker Hub to GitHub container registry to store the images for this action (Docker sunsets free plans for teams). **Use version 1.0.0** going forward as the previous versions will stop working once Docker removes the images from Docker hub (pull rate limits apply from 14.April 2023, removal on 14.May 2023)

## Workflow explanation
The action will upload all files (the `.github` folder and other files at the root folder are excluded) in the repository which have changed between the most recent commit and the previous commit on the default branch. Files for different storage account folders are uploaded to different Azure storage accounts. It expects and only works with the following folder structure (folder names can be arbitrary, and file extensions do not matter). The folder structure here as been made to illustrate the link between the repo structure and the Azure storage account setup:

```bash
├── .github
├── storageaccount1
│   ├── container1
│   │   ├── file1.json
│   ├── container2
│   │   ├── file1.yaml
│   │   ├── file2.json
├── storageaccount2
│   ├── container1
│   │   ├── file1.yml
```


The GitHub action connects to Azure storage accounts by using connection strings provided as environment variables. The environment variables must follow this naming convention:

```bash
STORAGEACCOUNT_STORAGE_ACCOUNT_CONNECTION_STRING
```
where `STORAGEACCOUNT` corresponds to the folder name in the repository. The action will match the folder names in the repository with the prefix used in the environment variables for the storage account connection string. The action creates one container per folder and will name that container like this:
```bash
STORAGEACCOUNT-CONTAINER
```
and each container will hold all files for that folder.

The action will assess changes only on the default branch (currently supported: `master` and `main`). The action should therefore only be run on commits to master, but not on other events, like e.g. pull requests. Changes are assessed by comparing commit SHAs and the action needs certain inputs to evaluate changed files. See [Inputs](#inputs) section.

## Inputs
The action does not need any inputs to the GitHub action, but the following environment variables need to be set:
| Variable name                             | Explanation                                                                                 |
|-------------------------------------------|---------------------------------------------------------------------------------------------|
| STORAGEACCOUNT1_STORAGE_ACCOUNT_CONNECTION_STRING | Azure storage account connection string for storageaccount1                                         |
| STORAGEACCOUNT2_STORAGE_ACCOUNT_CONNECTION_STRING | Azure storage account connection string for storageaccount2                                         |
| REPO_NAME                                 | Repository name to assess changes in, should be taken from the GitHub action events payload |
| REPOSITORY_ACCESS_TOKEN                   | Access token used to fetch repository content to assess changes                             |
| BRANCH_REF                                | Full branch name, should be taken from the GitHub action events payload                     |
| AFTER_COMMIT_SHA                          | After commit for assessing change, should be taken from the GitHub action events payload    |
| BEFORE_COMMIT_SHA                         | Before commit for assessing change, should be taken from the GitHub action events payload   |

## Usage
The sample workflow is based on the sample folder structure given above (2 storage account folders -> 2 environment variables for Azure storage accounts). Also note the values that are set for `REPO_NAME`, `BRANCH_REF`, `AFTER_COMMIT_SHA`, and `BEFORE_COMMIT_SHA`, these should be set exactly like below.

```yaml
name: Upload files

env:
  BRANCH_REF: ${{ github.event.ref }}
  REPO_NAME: ${{ github.event.repository.full_name }}
  BEFORE_COMMIT_SHA: ${{ github.event.before }}
  AFTER_COMMIT_SHA: ${{ github.event.after }}
  # make sure to set the the variables below as secrets or provide them in another secure way
  REPOSITORY_ACCESS_TOKEN: ${{ secrets.REPOSITORY_ACCESS_TOKEN }}
  STORAGEACCOUNT1_STORAGE_ACCOUNT_CONNECTION_STRING: ${{ secrets.STORAGEACCOUNT1_STORAGE_ACCOUNT_CONNECTION_STRING }}
  STORAGEACCOUNT2_STORAGE_ACCOUNT_CONNECTION_STRING: ${{ secrets.STORAGEACCOUNT2_STORAGE_ACCOUNT_CONNECTION_STRING }}


# Action runs on every commit to main (when a PR is merged), but does not need to run on opening/updating pull request
on:
  push:
    branches: [ main ]

jobs:
  validate-json:
    runs-on: ubuntu-latest

    steps:
    - uses: actions/checkout@v3
      with:
        fetch-depth: 2

    - name: Upload files
      uses: RaaLabs/azure-storage-upload-files@v1.0.0
```