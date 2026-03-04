"""URL cleaning utilities for removing tracking parameters (SPEC-021).

Uses the ural library for URL normalization combined with a comprehensive
list of known tracking parameters.
"""

from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
from typing import Dict, List

try:
    from ural import normalize_url
    URAL_AVAILABLE = True
except ImportError:
    URAL_AVAILABLE = False

# Known tracking parameters to remove
# This list supplements ural's built-in normalization
TRACKING_PARAMS = {
    # Google Analytics
    'utm_source', 'utm_medium', 'utm_campaign', 'utm_term', 'utm_content',
    'utm_id', 'utm_source_platform', 'utm_creative_format', 'utm_marketing_tactic',
    # Google Ads
    'gclid', 'gclsrc', 'dclid', 'gbraid', 'wbraid',
    # Facebook
    'fbclid', 'fb_action_ids', 'fb_action_types', 'fb_source', 'fb_ref',
    # Microsoft/Bing
    'msclkid',
    # Mailchimp
    'mc_eid', 'mc_cid',
    # HubSpot
    '_hsenc', '_hsmi', 'hsctaTracking',
    # Twitter/X
    'twclid', 's', 't',
    # Instagram
    'igshid',
    # YouTube
    'si', 'feature',
    # TikTok
    'tt_medium', 'tt_content',
    # LinkedIn
    'li_fat_id', 'li_id',
    # Pinterest
    'pin_source',
    # Reddit
    'share_id',
    # Snapchat
    'sc_cid',
    # Other common trackers
    'ref', 'ref_', 'source', 'yclid', '_ga', '_gl', 'trk',
    'tracking_id', 'share_source', 'campaign_id', 'ad_id',
    'affiliate_id', 'partner_id', 'promo_code',
}


def _is_tracking_param(param: str) -> bool:
    """Check if a parameter is a known tracking parameter."""
    param_lower = param.lower()
    # Check exact match
    if param_lower in TRACKING_PARAMS:
        return True
    # Check utm_ prefix (catch all UTM variants)
    if param_lower.startswith('utm_'):
        return True
    # Check common tracking prefixes
    if param_lower.startswith(('_ga', '_gl', '_hs')):
        return True
    return False


def analyze_url(url: str) -> Dict:
    """
    Analyze a URL and return cleaning information.

    Args:
        url: The URL to analyze

    Returns:
        dict with keys:
        - original_url: str - the input URL
        - cleaned_url: str - URL with tracking params removed
        - removed_params: list[str] - tracking params that were removed
        - is_clean: bool - True if no tracking params found and URL unchanged
        - has_tracking: bool - True if tracking params were found
    """
    if not url:
        return {
            'original_url': url,
            'cleaned_url': url,
            'removed_params': [],
            'is_clean': True,
            'has_tracking': False,
        }

    # Parse original URL
    parsed = urlparse(url)
    original_params = parse_qs(parsed.query, keep_blank_values=True)

    # Find tracking parameters
    removed_params: List[str] = []
    clean_params: Dict[str, List[str]] = {}

    for param, values in original_params.items():
        if _is_tracking_param(param):
            removed_params.append(param)
        else:
            clean_params[param] = values

    # Normalize domain (lowercase)
    normalized_netloc = parsed.netloc.lower()

    # Normalize path (remove trailing slash, except for root)
    normalized_path = parsed.path.rstrip('/') if parsed.path != '/' else '/'
    if not normalized_path:
        normalized_path = '/'

    # Rebuild query string (sorted for consistency)
    clean_query = urlencode(clean_params, doseq=True) if clean_params else ''

    # Rebuild URL without fragment
    cleaned_url = urlunparse((
        parsed.scheme,
        normalized_netloc,
        normalized_path,
        '',  # params (rarely used)
        clean_query,
        ''   # fragment removed
    ))

    # Use ural for additional normalization if available
    if URAL_AVAILABLE:
        try:
            cleaned_url = normalize_url(
                cleaned_url,
                strip_trailing_slash=True,
                strip_protocol=False,
                strip_irrelevant_subdomains=False,
                strip_fragment=True,
            )
        except Exception:
            pass  # Fall back to our normalization if ural fails

    # Check if URL is already clean
    is_clean = (
        len(removed_params) == 0 and
        url == cleaned_url
    )

    return {
        'original_url': url,
        'cleaned_url': cleaned_url,
        'removed_params': sorted(removed_params),
        'is_clean': is_clean,
        'has_tracking': len(removed_params) > 0,
    }


def clean_url(url: str) -> str:
    """
    Clean a URL by removing tracking parameters.

    Convenience function that returns just the cleaned URL.

    Args:
        url: The URL to clean

    Returns:
        The cleaned URL string
    """
    result = analyze_url(url)
    return result['cleaned_url']


def get_tracking_param_description(param: str) -> str:
    """
    Get a human-readable description of a tracking parameter.

    Args:
        param: The parameter name

    Returns:
        Description string
    """
    param_lower = param.lower()

    descriptions = {
        # Google Analytics
        'utm_source': 'Google Analytics (traffic source)',
        'utm_medium': 'Google Analytics (marketing medium)',
        'utm_campaign': 'Google Analytics (campaign name)',
        'utm_term': 'Google Analytics (search term)',
        'utm_content': 'Google Analytics (content variant)',
        # Ads
        'gclid': 'Google Ads click ID',
        'gbraid': 'Google Ads (iOS)',
        'wbraid': 'Google Ads (web-to-app)',
        'msclkid': 'Microsoft Ads click ID',
        'fbclid': 'Facebook click ID',
        'twclid': 'Twitter click ID',
        'igshid': 'Instagram share ID',
        # Other
        'si': 'YouTube share tracking',
        'feature': 'YouTube feature tracking',
        'mc_eid': 'Mailchimp email ID',
        'mc_cid': 'Mailchimp campaign ID',
    }

    if param_lower in descriptions:
        return descriptions[param_lower]
    if param_lower.startswith('utm_'):
        return 'Google Analytics parameter'
    if param_lower.startswith('_ga'):
        return 'Google Analytics cookie'
    if param_lower.startswith('_hs'):
        return 'HubSpot tracking'

    return 'Tracking parameter'
