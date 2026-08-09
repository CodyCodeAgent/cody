from scripts.check_docs import (
    check_cli_reference,
    check_config_reference,
    check_http_reference,
    check_local_links,
    check_python_fences,
    check_secrets_and_stale_commands,
    check_site_pages,
    markdown_files,
    site_files,
)


def test_repository_documentation_matches_public_surfaces():
    files = markdown_files()
    errors = [
        *check_local_links(files),
        *check_secrets_and_stale_commands(files),
        *check_python_fences(files),
        *check_site_pages(site_files()),
        *check_config_reference(),
        *check_cli_reference(),
        *check_http_reference(),
    ]
    assert errors == []
