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

    process_configuration_changed(
        repo=repo,
        branch_ref=branch_ref,
        previous_commit=before_commit_sha,
        this_commit=after_commit_sha,
    )


def process_configuration_changed(repo, branch_ref, previous_commit, this_commit):
    logging.info(f"Repo fetched. Comparing commits...")
    compared = repo.compare(previous_commit, this_commit)
    logging.info(f"Commits compared.")
    compared_files = list(
        filter(
            lambda f: len(f.filename.split("/")) >= 3
            and not f.filename.startswith(".github"),
            compared.files,
        )
    )  # Only consider files belonging to a tenant and device

    added_or_modified_files = list(
        filter(lambda f: f.status in {"added", "modified", "renamed"}, compared_files)
    )
    filenames_for_changed_files = ", ".join(
        list(map(lambda f: f.filename, added_or_modified_files))
    )

    if len(filenames_for_changed_files) == 0:
        logging.info("No changed files, no configurations updated.")
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
        logging.info(f"Change not on main branch, no configs updated.")
        return

    logging.info(f"Change on branch: {branch_ref}, updating configs")

    (
        files_for_tenants,
        changed_file_contents_for_tenant,
    ) = group_compared_files_and_changed_file_contents(
        compared_files, changed_file_contents
    )

    tenants = list(files_for_tenants.keys())

    for tenant in tenants:
        tenant_connection_string_env_variable = (
            f"{tenant.upper()}_STORAGE_ACCOUNT_CONNECTION_STRING"
        )
        tenant_storage_connection_string = os.environ.get(
            tenant_connection_string_env_variable
        )

        if tenant_storage_connection_string is not None:
            logging.info(f"Updating configs for tenant: {tenant}")
            update_blobs(
                compared_files=files_for_tenants[tenant],
                changed_file_contents=changed_file_contents_for_tenant[tenant],
                storage_connection_string=tenant_storage_connection_string,
            )
            logging.info(f"Finished updating configs for tenant: {tenant}")
        else:
            logging.info(
                f"Tenant: {tenant} does not have the connection string of the storage account set properly. Set the environment variable: {tenant.upper()}_STORAGE_ACCOUNT_CONNECTION_STRING in your workflow file"
            )
            logging.info(
                f"Configuration files are uploaded to general storage account (transition phase)"
            )

        general_storage_connection_string = os.environ.get(
            "STORAGE_ACCOUNT_CONNECTION_STRING"
        )
        if general_storage_connection_string is not None:
            # Do not upload twice to same storage account (transition phase)
            if tenant_storage_connection_string == general_storage_connection_string:
                continue

            # Update all configuration files in old storage container (transition phase)
            logging.info(
                f"Updating configs for tenant: {tenant} (old storage account, transition phase)"
            )
            update_blobs(
                compared_files=files_for_tenants[tenant],
                changed_file_contents=changed_file_contents_for_tenant[tenant],
                storage_connection_string=general_storage_connection_string,
            )
            logging.info(
                f"Finished updating configs for tenant: {tenant} (old storage account, transition phase)"
            )
        else:
            logging.info(
                f"General connection string of the storage account not set properly. Set the environment variable: STORAGE_ACCOUNT_CONNECTION_STRING in your workflow file"
            )

    logging.info(f"Finished updating all configurations for all tenants")


def update_blobs(compared_files, changed_file_contents, storage_connection_string):
    service = BlobServiceClient.from_connection_string(
        conn_str=storage_connection_string
    )

    for device, files in compared_files.items():
        container_client = service.get_container_client(device)
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
# The name will be on the format '<tenant>-<device>'
def get_container_name(filename):
    return "-".join(filename.split("/")[0:2]).replace(" ", "-").lower()


def get_tenant_name(filename):
    return filename.split("/")[0]


def group_compared_files_and_changed_file_contents(
    compared_files, changed_file_contents
):
    all_filenames = list(map(lambda f: f.filename, compared_files))
    # Creates a nested dictionary with the following format:
    # {"tenant": {"device": {"filename": File}}}
    files_for_tenants = dict(
        map(
            lambda f: (
                get_tenant_name(f),
                dict(
                    map(
                        lambda f: (get_container_name(f), dict()),
                        [x for x in all_filenames if x.startswith(get_tenant_name(f))],
                    )
                ),
            ),
            all_filenames,
        )
    )

    for file in compared_files:
        try:
            tenant, device, filename = file.filename.split("/")
            device = "-".join([tenant, device]).replace(" ", "-").lower()
            files_for_tenants[tenant][device][filename] = file
        except Exception:
            logging.error(f"Could not process file: {file.filename}")

    changed_file_contents_for_tenant = dict(
        map(lambda f: (get_tenant_name(f), dict()), changed_file_contents)
    )

    for key, value in changed_file_contents.items():
        tenant, device, filename = key.split("/")
        changed_file_contents_for_tenant[tenant][key] = value

    return files_for_tenants, changed_file_contents_for_tenant


if __name__ == "__main__":
    main()
