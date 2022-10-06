# upload-configurations
[![Build](https://github.com/RaaLabs/upload-configurations/actions/workflows/build.yml/badge.svg)](https://github.com/RaaLabs/upload-configurations/actions/workflows/build.yml)

GitHub action to upload configuration files to multiple Azure storage accounts.
## Workflow explanation
The action will upload all files (the `.github` folder and other files at the root folder are excluded) in the repository which have changed between the most recent commit and the previous commit on the default branch. Files for different tenants are uploaded to different Azure storage accounts. It expects and only works with the following folder structure (folder names can be arbitrary, and file extensions do not matter):

```bash
├── .github
├── tenant1
│   ├── device1
│   │   ├── configuration1.json
│   ├── device2
│   │   ├── configuration1.yaml
│   │   ├── configuration2.json
├── tenant2
│   ├── device1
│   │   ├── configuration1.yml
```


The GitHub action connects to Azure storage accounts by using connection strings provided as environment variables. The environment variables must follow this naming convention:

```bash
TENANT_STORAGE_ACCOUNT_CONNECTION_STRING
```
where `TENANT` corresponds to the folder name in the repository. The action will match the folder names in the repository with the prefix used in the environment variables for the storage account connection string. The action creates one container per device and will name that container like this:
```bash
TENANT-DEVICE
```
and each container will hold all configuration files for that device.

The action will assess changes only on the default branch (currently supported: `master` and `main`). The action should therefore only be run on commits to master, but not on other events, like e.g. pull requests. Changes are assessed by comparing commit SHAs and the action needs certain inputs to evaluate changed files. See [Inputs](#inputs) section.

## Inputs
The action does not need any inputs to the GitHub action, but the following environment variables need to be set:
| Variable name                             | Explanation                                                                                 |
|-------------------------------------------|---------------------------------------------------------------------------------------------|
| TENANT1_STORAGE_ACCOUNT_CONNECTION_STRING | Azure storage account connection string for tenant1                                         |
| TENANT2_STORAGE_ACCOUNT_CONNECTION_STRING | Azure storage account connection string for tenant2                                         |
| REPO_NAME                                 | Repository name to assess changes in, should be taken from the GitHub action events payload |
| REPOSITORY_ACCESS_TOKEN                   | Access token used to fetch repository content to assess changes                             |
| BRANCH_REF                                | Full branch name, should be taken from the GitHub action events payload                     |
| AFTER_COMMIT_SHA                          | After commit for assessing change, should be taken from the GitHub action events payload    |
| BEFORE_COMMIT_SHA                         | Before commit for assessing change, should be taken from the GitHub action events payload   |

## Usage
The sample workflow is based on the sample folder structure given above (2 tenants -> 2 environment variables for Azure storage accounts). Also note the values that are set for `REPO_NAME`, `BRANCH_REF`, `AFTER_COMMIT_SHA`, and `BEFORE_COMMIT_SHA`, these should be set exactly like below.

```yaml
name: Upload configurations

env:
  BRANCH_REF: ${{ github.event.ref }}
  REPO_NAME: ${{ github.event.repository.full_name }}
  BEFORE_COMMIT_SHA: ${{ github.event.before }}
  AFTER_COMMIT_SHA: ${{ github.event.after }}
  # make sure to set the the variables below as secrets or provide them in another secure way
  REPOSITORY_ACCESS_TOKEN: ${{ secrets.REPOSITORY_ACCESS_TOKEN }}
  TENANT1_STORAGE_ACCOUNT_CONNECTION_STRING: ${{ secrets.TENANT1_STORAGE_ACCOUNT_CONNECTION_STRING }}
  TENANT2_STORAGE_ACCOUNT_CONNECTION_STRING: ${{ secrets.TENANT2_STORAGE_ACCOUNT_CONNECTION_STRING }}


# Action runs on every commit to main (when a PR is merged), but does not need to run on opening/updating pull request
on:
  push:
    branches: [ main ]

jobs:
  validate-json:
    runs-on: ubuntu-latest

    steps:
    - uses: actions/checkout@v2
      with:
        fetch-depth: 2

    - name: Upload configurations
      uses: RaaLabs/upload-configurations@v0.0.1
```