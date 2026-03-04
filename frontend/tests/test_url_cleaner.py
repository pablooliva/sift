"""Tests for URL cleaning functionality (SPEC-021)."""

import pytest
import sys
from pathlib import Path

# Add utils directory to path to import url_cleaner directly
# This avoids importing the full utils package which requires streamlit
sys.path.insert(0, str(Path(__file__).parent.parent / "utils"))

from url_cleaner import analyze_url, clean_url, get_tracking_param_description


class TestAnalyzeUrl:
    """Test URL analysis function."""

    def test_clean_url_unchanged(self):
        """Clean URLs should pass through unchanged."""
        url = "https://example.com/article"
        result = analyze_url(url)
        assert result['is_clean'] is True
        assert result['has_tracking'] is False
        assert result['removed_params'] == []

    def test_empty_url(self):
        """Empty URL should return empty result."""
        result = analyze_url("")
        assert result['is_clean'] is True
        assert result['cleaned_url'] == ""

    def test_utm_source_removed(self):
        """utm_source should be removed."""
        url = "https://example.com/page?utm_source=twitter"
        result = analyze_url(url)
        assert result['has_tracking'] is True
        assert 'utm_source' in result['removed_params']
        assert 'utm_source' not in result['cleaned_url']
        assert result['cleaned_url'] == "https://example.com/page"

    def test_utm_params_removed(self):
        """All UTM parameters should be removed."""
        url = "https://example.com/page?utm_source=twitter&utm_medium=social&utm_campaign=spring"
        result = analyze_url(url)
        assert result['has_tracking'] is True
        assert 'utm_source' in result['removed_params']
        assert 'utm_medium' in result['removed_params']
        assert 'utm_campaign' in result['removed_params']
        assert result['cleaned_url'] == "https://example.com/page"

    def test_fbclid_removed(self):
        """Facebook click ID should be removed."""
        url = "https://example.com/page?fbclid=abc123xyz"
        result = analyze_url(url)
        assert result['has_tracking'] is True
        assert 'fbclid' in result['removed_params']
        assert 'fbclid' not in result['cleaned_url']

    def test_gclid_removed(self):
        """Google Ads click ID should be removed."""
        url = "https://example.com/page?gclid=abc123"
        result = analyze_url(url)
        assert result['has_tracking'] is True
        assert 'gclid' in result['removed_params']

    def test_msclkid_removed(self):
        """Microsoft Ads click ID should be removed."""
        url = "https://example.com/page?msclkid=xyz789"
        result = analyze_url(url)
        assert result['has_tracking'] is True
        assert 'msclkid' in result['removed_params']

    def test_functional_params_preserved(self):
        """Non-tracking params should be preserved."""
        url = "https://shop.com/product?id=456&color=red&utm_campaign=sale"
        result = analyze_url(url)
        assert result['has_tracking'] is True
        assert 'utm_campaign' in result['removed_params']
        assert 'id=456' in result['cleaned_url']
        assert 'color=red' in result['cleaned_url']
        assert 'utm_campaign' not in result['cleaned_url']

    def test_mixed_params_order_preserved(self):
        """Mix of tracking and functional params."""
        url = "https://example.com/search?q=test&page=2&gclid=abc&msclkid=xyz"
        result = analyze_url(url)
        assert result['has_tracking'] is True
        assert 'gclid' in result['removed_params']
        assert 'msclkid' in result['removed_params']
        assert 'q=test' in result['cleaned_url']
        assert 'page=2' in result['cleaned_url']

    def test_domain_normalized_to_lowercase(self):
        """Domain should be lowercased."""
        url = "https://EXAMPLE.COM/Page"
        result = analyze_url(url)
        assert 'example.com' in result['cleaned_url']

    def test_fragment_removed(self):
        """URL fragments should be removed."""
        url = "https://example.com/page#section"
        result = analyze_url(url)
        assert '#' not in result['cleaned_url']

    def test_trailing_slash_removed(self):
        """Trailing slashes should be normalized."""
        url = "https://example.com/page/"
        result = analyze_url(url)
        # Should end with /page (no trailing slash)
        assert result['cleaned_url'].endswith('/page')

    def test_root_path_preserved(self):
        """Root path should keep single slash."""
        url = "https://example.com/"
        result = analyze_url(url)
        assert result['cleaned_url'] in ["https://example.com", "https://example.com/"]

    def test_youtube_si_removed(self):
        """YouTube share tracking should be removed."""
        url = "https://youtube.com/watch?v=abc123&si=xyz789"
        result = analyze_url(url)
        assert 'si' in result['removed_params']
        assert 'v=abc123' in result['cleaned_url']

    def test_instagram_igshid_removed(self):
        """Instagram share ID should be removed."""
        url = "https://instagram.com/p/abc123?igshid=xyz"
        result = analyze_url(url)
        assert 'igshid' in result['removed_params']

    def test_twitter_twclid_removed(self):
        """Twitter click ID should be removed."""
        url = "https://twitter.com/user/status/123?twclid=abc"
        result = analyze_url(url)
        assert 'twclid' in result['removed_params']

    def test_mailchimp_params_removed(self):
        """Mailchimp tracking params should be removed."""
        url = "https://example.com/page?mc_eid=abc&mc_cid=xyz"
        result = analyze_url(url)
        assert 'mc_eid' in result['removed_params']
        assert 'mc_cid' in result['removed_params']

    def test_all_params_tracking_returns_base_url(self):
        """If all params are tracking, return base URL only."""
        url = "https://t.co/abc123?utm_source=twitter&fbclid=xyz"
        result = analyze_url(url)
        assert result['has_tracking'] is True
        assert result['cleaned_url'] == "https://t.co/abc123"

    def test_url_with_port(self):
        """URLs with ports should be handled correctly."""
        url = "https://example.com:8080/page?utm_source=test"
        result = analyze_url(url)
        assert ':8080' in result['cleaned_url']
        assert 'utm_source' not in result['cleaned_url']

    def test_url_with_authentication(self):
        """URLs with user:pass should be handled."""
        url = "https://user:pass@example.com/page?utm_source=test"
        result = analyze_url(url)
        assert 'user:pass@' in result['cleaned_url']
        assert 'utm_source' not in result['cleaned_url']

    def test_custom_utm_variants_removed(self):
        """Custom UTM variants (utm_*) should be removed."""
        url = "https://example.com/page?utm_custom_param=value"
        result = analyze_url(url)
        assert 'utm_custom_param' in result['removed_params']

    def test_ga_params_removed(self):
        """Google Analytics _ga params should be removed."""
        url = "https://example.com/page?_ga=1.234.567&_gl=abc"
        result = analyze_url(url)
        assert '_ga' in result['removed_params']
        assert '_gl' in result['removed_params']


class TestCleanUrl:
    """Test convenience clean_url function."""

    def test_returns_string(self):
        """Should return just the cleaned URL string."""
        url = "https://example.com/page?utm_source=test"
        result = clean_url(url)
        assert isinstance(result, str)
        assert 'utm_source' not in result

    def test_clean_url_matches_analyze(self):
        """clean_url should match analyze_url['cleaned_url']."""
        url = "https://example.com/page?fbclid=abc&id=123"
        assert clean_url(url) == analyze_url(url)['cleaned_url']


class TestGetTrackingParamDescription:
    """Test tracking parameter descriptions."""

    def test_known_param_description(self):
        """Known params should have descriptions."""
        assert 'Google Analytics' in get_tracking_param_description('utm_source')
        assert 'Facebook' in get_tracking_param_description('fbclid')
        assert 'Google Ads' in get_tracking_param_description('gclid')

    def test_utm_prefix_description(self):
        """UTM params should get generic description."""
        desc = get_tracking_param_description('utm_custom')
        assert 'Google Analytics' in desc

    def test_unknown_param_description(self):
        """Unknown params should get generic description."""
        desc = get_tracking_param_description('unknown_tracker')
        assert 'Tracking parameter' in desc


class TestRealWorldUrls:
    """Test with real-world URL patterns."""

    def test_newsletter_link(self):
        """Newsletter links often have many tracking params."""
        url = (
            "https://blog.example.com/article-title"
            "?utm_source=newsletter"
            "&utm_medium=email"
            "&utm_campaign=weekly_digest"
            "&utm_content=header_link"
            "&mc_eid=abc123"
        )
        result = analyze_url(url)
        assert result['has_tracking'] is True
        assert len(result['removed_params']) == 5
        assert result['cleaned_url'] == "https://blog.example.com/article-title"

    def test_social_share_link(self):
        """Social media share links."""
        url = "https://example.com/product?ref=twitter&fbclid=abc&source=social"
        result = analyze_url(url)
        assert 'fbclid' in result['removed_params']
        assert 'ref' in result['removed_params']
        assert 'source' in result['removed_params']

    def test_google_ads_landing(self):
        """Google Ads landing page URLs."""
        url = "https://shop.example.com/sale?gclid=abc&gbraid=xyz&utm_source=google"
        result = analyze_url(url)
        assert 'gclid' in result['removed_params']
        assert 'gbraid' in result['removed_params']
        assert 'utm_source' in result['removed_params']

    def test_ecommerce_with_functional_params(self):
        """E-commerce URL with product params and tracking."""
        url = (
            "https://shop.example.com/products/item"
            "?sku=ABC123"
            "&size=large"
            "&color=blue"
            "&utm_source=instagram"
            "&igshid=xyz"
        )
        result = analyze_url(url)
        assert 'sku=ABC123' in result['cleaned_url']
        assert 'size=large' in result['cleaned_url']
        assert 'color=blue' in result['cleaned_url']
        assert 'utm_source' not in result['cleaned_url']
        assert 'igshid' not in result['cleaned_url']
