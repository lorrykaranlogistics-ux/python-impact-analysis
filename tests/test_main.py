from main import normalize_repo


def test_normalize_repo_owner_repo():
    assert normalize_repo("my-org/order-service") == "my-org/order-service"


def test_normalize_repo_http_url():
    assert normalize_repo("https://github.com/my-org/order-service") == "my-org/order-service"


def test_normalize_repo_gitlab_url_with_duplicates():
    inp = "https://gitlab.com/sivamanismca/micro-service-usershttps://gitlab.com/sivamanismca/micro-service-users"
    assert normalize_repo(inp) == "sivamanismca/micro-service-users"


def test_normalize_repo_with_host_prefix():
    assert normalize_repo("gitlab.com/sivamanismca/micro-service-users") == "sivamanismca/micro-service-users"


def test_is_gitlab_repo_from_url():
    from main import is_gitlab_repo

    assert is_gitlab_repo("https://gitlab.com/sivamanismca/micro-service-users")
    assert is_gitlab_repo("gitlab.com/sivamanismca/micro-service-users")
    assert not is_gitlab_repo("https://github.com/my-org/repo")
