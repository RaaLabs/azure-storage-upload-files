import os
import logging
from github import Github
from azure.storage.blob import BlobServiceClient


def main():
    logging.basicConfig(
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        level=logging.INFO,
    )

    repo_access_token = os.environ["REPOSITORY_ACCESS_TOKEN"]
    repo_name = os.environ["REPO_NAME"]
    branch_ref = os.environ["BRANCH_REF"]
    after_commit_sha = os.environ["AFTER_COMMIT_SHA"]
    before_commit_sha = os.environ["BEFORE_COMMIT_SHA"]

    logging.info(f"Repository name: {repo_name}")
    logging.info(f"Branch ref: {branch_ref}")
    logging.info(f"After commit sha: {after_commit_sha}")
    logging.info(f"Before commit sha: {before_commit_sha}")

    logging.info(f"Connecting to github...")
    g = Github(repo_access_token)
    logging.info(f"Fetching repo {repo_name}...")
    repo = g.get_repo(repo_name)

    process_files_changed(
        repo=repo,
        branch_ref=branch_ref,
        previous_commit=before_commit_sha,
        this_commit=after_commit_sha,
    )


def process_files_changed(repo, branch_ref, previous_commit, this_commit):
    logging.info(f"Repo fetched. Comparing commits...")
    compared = repo.compare(previous_commit, this_commit)
    logging.info(f"Commits compared.")
    compared_files = list(
        filter(
            lambda f: len(f.filename.split("/")) >= 3
            and not f.filename.startswith(".github"),
            compared.files,
        )
    )

    added_or_modified_files = list(
        filter(lambda f: f.status in {"added", "modified", "renamed"}, compared_files)
    )
    filenames_for_changed_files = ", ".join(
        list(map(lambda f: f.filename, added_or_modified_files))
    )

    if len(filenames_for_changed_files) == 0:
        logging.info("No changed files, no files updated.")
        return

    logging.info(f"Changed files: {filenames_for_changed_files}")
    # get_contents might take long if a lot of files have been changed
    changed_file_contents = dict(
        map(
            lambda f: (
                f.filename,
                repo.get_contents(f.filename, this_commit).decoded_content,
            ),
            added_or_modified_files,
        )
    )

    allowed_branches = ["refs/heads/master", "refs/heads/main"]
    if branch_ref not in allowed_branches:
        logging.info(f"Change not on main branch, no files updated.")
        return

    logging.info(f"Change on branch: {branch_ref}, updating files")

    (
        files_for_storage_accounts,
        changed_file_contents_for_storage_accounts,
    ) = group_compared_files_and_changed_file_contents(
        compared_files, changed_file_contents
    )

    storage_accounts = list(files_for_storage_accounts.keys())

    for storage_account in storage_accounts:
        storage_account_connection_string_env_variable = (
            f"{storage_account.upper()}_STORAGE_ACCOUNT_CONNECTION_STRING"
        )
        storage_account_connection_string = os.environ.get(
            storage_account_connection_string_env_variable
        )

        if storage_account_connection_string is not None:
            logging.info(f"Updating files for storage account: {storage_account}")
            update_blobs(
                compared_files=files_for_storage_accounts[storage_account],
                changed_file_contents=changed_file_contents_for_storage_accounts[storage_account],
                storage_connection_string=storage_account_connection_string,
            )
            logging.info(f"Finished updating files for storage account: {storage_account}")
        else:
            logging.info(
                f"Storage account: {storage_account} does not have the connection string of the storage account set properly. Set the environment variable: {storage_account.upper()}_STORAGE_ACCOUNT_CONNECTION_STRING in your workflow file"
            )
            logging.info(
                f"Files are uploaded to general storage account (transition phase)"
            )

        general_storage_account_connection_string = os.environ.get(
            "STORAGE_ACCOUNT_CONNECTION_STRING"
        )
        if general_storage_account_connection_string is not None:
            # Do not upload twice to same storage account (transition phase)
            if storage_account_connection_string == general_storage_account_connection_string:
                continue

            # Update all files files in old storage container (transition phase)
            logging.info(
                f"Updating files for storage account: {storage_account} (old storage account, transition phase)"
            )
            update_blobs(
                compared_files=files_for_storage_accounts[storage_account],
                changed_file_contents=changed_file_contents_for_storage_accounts[storage_account],
                storage_connection_string=general_storage_account_connection_string,
            )
            logging.info(
                f"Finished updating files for storage account: {storage_account} (old storage account, transition phase)"
            )
        else:
            logging.info(
                f"General connection string of the storage account not set properly. Set the environment variable: STORAGE_ACCOUNT_CONNECTION_STRING in your workflow file"
            )

    logging.info(f"Finished updating all files for all storage accounts")


def update_blobs(compared_files, changed_file_contents, storage_connection_string):
    service = BlobServiceClient.from_connection_string(
        conn_str=storage_connection_string
    )

    for container, files in compared_files.items():
        container_client = service.get_container_client(container)
        try:
            # Create the container if it does not exist
            container_client.create_container()
        except:
            pass
        container_client.set_container_metadata(
            metadata={
                "bump": "This property is overwritten to bump container last modified timestamp"
            }
        )
        for filename, file in files.items():
            logging.info(f"File changed: {file.filename}, status: {file.status}")
            blob_client = container_client.get_blob_client(filename)
            if file.status in {"added", "modified", "renamed"}:
                content = changed_file_contents[file.filename]
                blob_client.upload_blob(content, overwrite=True)
                logging.info(
                    f"File: {file.filename} uploaded to Azure storage account: {get_container_name(file.filename)}"
                )
            elif file.status in {"removed"}:
                blob_client.delete_blob()
                logging.info(
                    f"File: {file.filename} deleted from Azure storage account: {get_container_name(file.filename)}."
                )

                # if container is empty, delete container
                remaining_blobs = sum(
                    1 for _ in container_client.list_blobs()
                )  # lazy list, must iterate to get size
                if remaining_blobs == 0:
                    container_client.delete_container()


# Generate a blob container name from filename.
# The name will be on the format '<storageaccount>-<container>'
def get_container_name(filename):
    return "-".join(filename.split("/")[0:2]).replace(" ", "-").lower()


def get_storage_account_name(filename):
    return filename.split("/")[0]


def group_compared_files_and_changed_file_contents(
    compared_files, changed_file_contents
):
    all_filenames = list(map(lambda f: f.filename, compared_files))
    # Creates a nested dictionary with the following format:
    # {"storageaccount": {"container": {"filename": File}}}
    files_for_storage_accounts = dict(
        map(
            lambda f: (
                get_storage_account_name(f),
                dict(
                    map(
                        lambda f: (get_container_name(f), dict()),
                        [x for x in all_filenames if x.startswith(get_storage_account_name(f))],
                    )
                ),
            ),
            all_filenames,
        )
    )

    for file in compared_files:
        try:
            storage_account, container, filename = file.filename.split("/")
            container = "-".join([storage_account, container]).replace(" ", "-").lower()
            files_for_storage_accounts[storage_account][container][filename] = file
        except Exception:
            logging.error(f"Could not process file: {file.filename}")

    changed_file_contents_for_storage_account = dict(
        map(lambda f: (get_storage_account_name(f), dict()), changed_file_contents)
    )

    for key, value in changed_file_contents.items():
        storage_account, container, filename = key.split("/")
        changed_file_contents_for_storage_account[storage_account][key] = value

    return files_for_storage_accounts, changed_file_contents_for_storage_account


if __name__ == "__main__":
    main()
