"""
GitHub Client for authenticating and interacting with the GitHub API.
"""
import os
import time
import jwt
import requests
import logging
from requests import HTTPError

REQUEST_TIMEOUT = 30  # seconds

logger = logging.getLogger(__name__)


class GitHubClient:
    """Client for authenticated interactions with the GitHub API as a GitHub App."""

    def __init__(self):
        """Initialize GitHubClient with environment configuration."""
        self.app_id = os.environ.get('GITHUB_APP_ID')
        self.installation_id = os.environ.get('GITHUB_INSTALLATION_ID')
        self.private_key = os.environ.get('GITHUB_PRIVATE_KEY')
        self.private_key_path = os.environ.get('GITHUB_PRIVATE_KEY_PATH')
        self.project_id = os.environ.get('GOOGLE_CLOUD_PROJECT')

        if not all([self.app_id, self.installation_id]) or not (self.private_key_path or self.private_key):
            logger.warning("GitHub App configuration missing.")

    def _get_private_key(self):
        """
        Retrieve the GitHub App private key.

        Returns:
            str: The private key content.

        Raises:
            ValueError: If no private key source is configured.
        """
        # Retrun environment variable
        if self.private_key:
            return self.private_key
        # Return file content
        elif self.private_key_path:
            with open(self.private_key_path, 'r') as f:
                return f.read()
        else:
            raise ValueError("No private key source configured.")

    def _generate_jwt(self):
        """Generates a JWT for GitHub App authentication."""
        try:
            private_key = self._get_private_key()

            payload = {
                'iat': int(time.time()),
                'exp': int(time.time()) + (10 * 60),
                'iss': self.app_id
            }

            encoded_jwt = jwt.encode(payload, private_key, algorithm='RS256')
            return encoded_jwt
        except Exception as e:
            logger.error(f"Error generating JWT: {e}")
            raise

    def get_installation_access_token(self):
        """Obtains an installation access token."""
        # https://docs.github.com/en/apps/creating-github-apps/authenticating-with-a-github-app/generating-an-installation-access-token-for-a-github-app
        jwt_token = self._generate_jwt()
        headers = self._build_headers(jwt_token)
        url = f'https://api.github.com/app/installations/{self.installation_id}/access_tokens'

        response = requests.post(url, headers=headers, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        # The installation access token will expire after 1 hour.
        return response.json()['token']

    def _build_headers(self, token):
        """Build standard GitHub API headers for the current REST API version."""
        return {
            'Authorization': f'Bearer {token}',
            'Accept': 'application/vnd.github+json',
            'X-GitHub-Api-Version': '2026-03-10'
        }

    def _get_runner_group_id(self, org_name, runner_group_name=None):
        """Resolve a runner group ID by name for an organization."""
        token = self.get_installation_access_token()
        headers = self._build_headers(token)
        url = f'https://api.github.com/orgs/{org_name}/actions/runner-groups'
        params = {'per_page': 100}

        response = requests.get(url, headers=headers, params=params, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()

        group_name = (runner_group_name or 'Default').strip().lower()
        for runner_group in response.json().get('runner_groups', []):
            if runner_group.get('name', '').strip().lower() == group_name:
                return runner_group['id']

        raise ValueError(f"Runner group '{runner_group_name or 'Default'}' not found for organization '{org_name}'")

    def get_jit_config(self, runner_name, labels, org_name=None, repo_name=None, runner_group_name=None):
        """Generate an encoded JIT config for a self-hosted runner."""
        if not runner_name:
            raise ValueError("runner_name is required")

        if not labels:
            raise ValueError("labels are required")

        token = self.get_installation_access_token()
        headers = self._build_headers(token)

        if org_name:
            runner_group_id = self._get_runner_group_id(org_name, runner_group_name)
            url = f'https://api.github.com/orgs/{org_name}/actions/runners/generate-jitconfig'
            logger.info("Create JIT config for organization runner: %s", org_name)
        elif repo_name:
            repo_owner = repo_name.split('/')[0]
            runner_group_id = self._get_runner_group_id(repo_owner, runner_group_name)
            url = f'https://api.github.com/repos/{repo_name}/actions/runners/generate-jitconfig'
            logger.info("Create JIT config for repository runner: %s", repo_name)
        else:
            raise ValueError("Either org_name or repo_name must be provided")

        payload = {
            'name': runner_name,
            'runner_group_id': runner_group_id,
            'labels': labels,
            'work_folder': '_work'
        }

        response = requests.post(url, headers=headers, json=payload, timeout=REQUEST_TIMEOUT)

        try:
            response.raise_for_status()
        except HTTPError as exc:
            logger.warning("Failed to create JIT config for runner %s: %s", runner_name, exc)
            raise

        return response.json()['encoded_jit_config']
