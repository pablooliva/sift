"""
Settings Page Object for Playwright E2E tests (SPEC-025).

Provides locators and actions for the Settings page:
- Auto-classification toggle
- Confidence threshold sliders
- Label management (add/remove)
- Reset to defaults
"""

from playwright.sync_api import Page, expect
from .base_page import BasePage


class SettingsPage(BasePage):
    """Page Object for Settings page."""

    def __init__(self, page: Page):
        super().__init__(page)

    # =========================================================================
    # Navigation
    # =========================================================================

    def navigate(self):
        """Navigate to the Settings page."""
        self.goto("Settings")
        self._wait_for_streamlit_ready()

    # =========================================================================
    # Page-specific Locators - Header
    # =========================================================================

    @property
    def page_title(self):
        """Get the page title."""
        return self.page.locator('[data-testid="stHeading"]:has-text("Settings")')

    # =========================================================================
    # Page-specific Locators - Auto-Classification Toggle
    # =========================================================================

    @property
    def classification_toggle(self):
        """Get the auto-classification toggle."""
        return self.page.locator('[data-testid="stCheckbox"]').filter(
            has=self.page.locator('text=/Enable auto-classification/i')
        ).locator('input[type="checkbox"]')

    @property
    def classification_toggle_label(self):
        """Get the auto-classification toggle label for clicking."""
        # Use more flexible text matching (case-insensitive, partial match)
        return self.page.locator('[data-testid="stCheckbox"]').filter(
            has_text="auto-classification"
        ).locator('label').first

    @property
    def classification_enabled_info(self):
        """Get the info message shown when classification is enabled."""
        return self.page.get_by_text("Documents will be automatically classified")

    @property
    def classification_disabled_warning(self):
        """Get the warning message shown when classification is disabled."""
        return self.page.get_by_text("Auto-classification is disabled")

    # =========================================================================
    # Page-specific Locators - Threshold Sliders
    # =========================================================================

    @property
    def auto_apply_threshold_slider(self):
        """Get the auto-apply threshold slider."""
        return self.page.locator('[data-testid="stSlider"]').filter(
            has=self.page.locator('text=/Auto-apply threshold/i')
        )

    @property
    def suggestion_threshold_slider(self):
        """Get the suggestion threshold slider."""
        return self.page.locator('[data-testid="stSlider"]').filter(
            has=self.page.locator('text=/Suggestion threshold/i')
        )

    @property
    def auto_apply_metric(self):
        """Get the auto-apply threshold preview metric."""
        return self.page.locator('[data-testid="stMetric"]').filter(has_text="Auto-applied")

    @property
    def suggestion_metric(self):
        """Get the suggestion threshold preview metric."""
        return self.page.locator('[data-testid="stMetric"]').filter(has_text="Suggested")

    @property
    def hidden_metric(self):
        """Get the hidden threshold preview metric."""
        return self.page.locator('[data-testid="stMetric"]').filter(has_text="Hidden")

    # =========================================================================
    # Page-specific Locators - Label Management
    # =========================================================================

    @property
    def labels_section(self):
        """Get the Classification Labels section."""
        return self.page.get_by_text("Classification Labels").locator('..')

    @property
    def label_count_text(self):
        """Get the label count text."""
        return self.page.locator('text=/\\d+ labels configured/i')

    @property
    def label_items(self):
        """Get all label items displayed."""
        return self.page.locator('text=/^.*$/:near(button:has-text(""))').filter(
            has=self.page.locator('[data-testid="stButton"]')
        )

    def get_label_element(self, label_name: str):
        """Get a specific label element by name."""
        return self.page.locator(f'text="{label_name}"').first

    def get_label_delete_button(self, label_name: str):
        """Get the delete button for a specific label."""
        return self.page.locator(f'button[key*="delete_{label_name}"]').or_(
            self.page.locator(f'button:has-text("")').filter(
                has=self.page.locator(f'[title*="Delete"]')
            ).near(self.page.locator(f'text="{label_name}"'))
        )

    @property
    def new_label_input(self):
        """Get the new label input field."""
        return self.page.locator('input[placeholder*="urgent"]').or_(
            self.page.locator('label:has-text("Label name")').locator('..').locator('input')
        )

    @property
    def add_label_button(self):
        """Get the Add Label button."""
        return self.page.locator('button:has-text("➕ Add Label")')

    # =========================================================================
    # Page-specific Locators - Reset Buttons
    # =========================================================================

    @property
    def reset_labels_button(self):
        """Get the Reset Labels to Default button."""
        return self.page.locator('button:has-text("🔄 Reset Labels to Default")')

    @property
    def reset_thresholds_button(self):
        """Get the Reset Thresholds button."""
        return self.page.locator('button:has-text("🔄 Reset Thresholds")')

    # =========================================================================
    # Page-specific Locators - Expandable Sections
    # =========================================================================

    @property
    def about_expander(self):
        """Get the About Auto-Classification expander."""
        return self.page.locator('[data-testid="stExpander"]').filter(
            has=self.page.locator('text=/About Auto-Classification/i')
        )

    @property
    def technical_details_expander(self):
        """Get the Technical Details expander."""
        return self.page.locator('[data-testid="stExpander"]').filter(
            has=self.page.locator('text=/Technical Details/i')
        )

    # =========================================================================
    # Page-specific Locators - Messages
    # =========================================================================

    @property
    def success_messages(self):
        """Get success message elements."""
        return self.page.locator('[data-testid="stAlert"]').filter(has_text="")

    def get_success_message(self, text: str):
        """Get a success message containing specific text."""
        return self.page.get_by_text(text)

    # =========================================================================
    # Actions - Classification Toggle
    # =========================================================================

    def toggle_classification(self):
        """Toggle the auto-classification setting.

        Note: Streamlit 1.53+ has issues with subsequent clicks after page reruns.
        We use MouseEvent dispatch which triggers React's event handlers properly.
        For the second toggle, we need to dispatch the event on a freshly queried element.
        """
        # Use MouseEvent dispatch which triggers Streamlit's rerun
        self.page.evaluate('''() => {
            const checkbox = document.querySelector('[data-testid="stCheckbox"] input[type="checkbox"]');
            if (checkbox) {
                const event = new MouseEvent('click', {
                    bubbles: true,
                    cancelable: true,
                    view: window
                });
                checkbox.dispatchEvent(event);
            }
        }''')
        self.page.wait_for_timeout(2000)
        self._wait_for_spinners_gone()

    def enable_classification(self):
        """Enable auto-classification if disabled.

        Note: Streamlit has issues with multiple toggles per page load.
        If we can't enable with a toggle, we navigate away and back to reset state.
        """
        if not self.is_classification_enabled():
            self.toggle_classification()
            # Verify the toggle worked
            self.page.wait_for_timeout(500)
            if not self.is_classification_enabled():
                # Toggle didn't work - navigate away and back (resets to default: enabled)
                current_url = self.page.url
                self.page.goto(current_url.replace('/Settings', '/'))
                self.page.wait_for_timeout(500)
                self.page.goto(current_url)
                self._wait_for_streamlit_ready()

    def disable_classification(self):
        """Disable auto-classification if enabled.

        Note: Streamlit has issues with multiple toggles per page load.
        If we can't disable with a toggle, we navigate away, back, then toggle.
        """
        if self.is_classification_enabled():
            self.toggle_classification()
            # Verify the toggle worked
            self.page.wait_for_timeout(500)
            if self.is_classification_enabled():
                # Toggle didn't work - navigate away, back, then try once more
                current_url = self.page.url
                self.page.goto(current_url.replace('/Settings', '/'))
                self.page.wait_for_timeout(500)
                self.page.goto(current_url)
                self._wait_for_streamlit_ready()
                # Now try toggling again (fresh page load)
                if self.is_classification_enabled():
                    self.toggle_classification()

    def is_classification_enabled(self) -> bool:
        """Check if classification is currently enabled."""
        toggle = self.classification_toggle
        if toggle.count() > 0:
            return toggle.is_checked()
        return False

    # =========================================================================
    # Actions - Threshold Sliders
    # =========================================================================

    def set_auto_apply_threshold(self, value: int):
        """
        Set the auto-apply threshold.

        Args:
            value: Threshold value (50-100)

        Note: Streamlit 1.53+ uses div[role=slider] instead of input[type=range].
        We use keyboard navigation to set values.
        """
        slider = self.auto_apply_threshold_slider.locator('[role="slider"]')
        current = self.get_auto_apply_threshold()
        diff = value - current
        slider.focus()
        # Each arrow key moves by step (5 for this slider)
        steps = abs(diff) // 5
        key = "ArrowRight" if diff > 0 else "ArrowLeft"
        for _ in range(steps):
            slider.press(key)
        self.page.wait_for_timeout(300)

    def set_suggestion_threshold(self, value: int):
        """
        Set the suggestion threshold.

        Args:
            value: Threshold value (40 to auto_apply_threshold)

        Note: Streamlit 1.53+ uses div[role=slider] instead of input[type=range].
        """
        slider = self.suggestion_threshold_slider.locator('[role="slider"]')
        current = self.get_suggestion_threshold()
        diff = value - current
        slider.focus()
        steps = abs(diff) // 5
        key = "ArrowRight" if diff > 0 else "ArrowLeft"
        for _ in range(steps):
            slider.press(key)
        self.page.wait_for_timeout(300)

    def get_auto_apply_threshold(self) -> int:
        """Get the current auto-apply threshold value."""
        slider = self.auto_apply_threshold_slider.locator('[role="slider"]')
        if slider.count() > 0:
            value = slider.get_attribute('aria-valuenow')
            return int(value) if value else 85
        return 85

    def get_suggestion_threshold(self) -> int:
        """Get the current suggestion threshold value."""
        slider = self.suggestion_threshold_slider.locator('[role="slider"]')
        if slider.count() > 0:
            value = slider.get_attribute('aria-valuenow')
            return int(value) if value else 60
        return 60

    # =========================================================================
    # Actions - Label Management
    # =========================================================================

    def add_label(self, label_name: str):
        """
        Add a new classification label.

        Args:
            label_name: Name of the label to add

        Note: We must wait for the input to be enabled after page reruns,
        and for the button to be enabled after filling the input.
        Streamlit needs the input to lose focus to process the change.
        """
        # Wait for input to be enabled (after classification toggle)
        expect(self.new_label_input).to_be_enabled(timeout=5000)
        self.new_label_input.fill(label_name)

        # Press Tab to blur the input and trigger Streamlit's change processing
        self.new_label_input.press("Tab")

        # Wait for Streamlit to process the input change and rerender
        self.page.wait_for_timeout(1000)
        self._wait_for_spinners_gone()

        # Wait for add button to be enabled (Streamlit enables after input has content)
        expect(self.add_label_button).to_be_enabled(timeout=5000)
        self.add_label_button.click()
        self.page.wait_for_timeout(500)
        self._wait_for_spinners_gone()

    def remove_label(self, label_name: str):
        """
        Remove a classification label.

        Args:
            label_name: Name of the label to remove
        """
        # Find delete button near the label
        delete_btn = self.page.locator(f'button[key="delete_{label_name}"]').or_(
            self.page.locator('button:has-text("")').filter(
                has=self.page.locator('text=/delete/i, text=/')
            ).nth(0)
        )

        if delete_btn.count() > 0:
            delete_btn.click()
            self.page.wait_for_timeout(500)
            self._wait_for_spinners_gone()

    def get_label_count(self) -> int:
        """Get the number of configured labels."""
        count_text = self.label_count_text
        if count_text.count() > 0:
            import re
            text = count_text.text_content()
            match = re.search(r'(\d+)', text)
            if match:
                return int(match.group(1))
        return 0

    def has_label(self, label_name: str) -> bool:
        """Check if a label exists."""
        label = self.get_label_element(label_name)
        return label.count() > 0

    # =========================================================================
    # Actions - Reset
    # =========================================================================

    def reset_labels_to_default(self):
        """Reset labels to default configuration.

        Note: Must wait for button to be enabled after classification toggle.
        After click, st.rerun() causes full page reload - wait for it to complete.
        """
        expect(self.reset_labels_button).to_be_visible(timeout=5000)

        # Use JavaScript click to ensure the event triggers Streamlit's handler
        self.page.evaluate('''() => {
            const buttons = document.querySelectorAll('button');
            for (const btn of buttons) {
                if (btn.textContent.includes('Reset Labels to Default')) {
                    btn.click();
                    return true;
                }
            }
            return false;
        }''')

        # st.rerun() causes full page reload - wait for it to complete
        self.page.wait_for_timeout(2000)
        self._wait_for_spinners_gone()
        self._wait_for_streamlit_ready()

    def reset_thresholds(self):
        """Reset thresholds to default values.

        Note: Must wait for button to be enabled after classification toggle.
        After click, st.rerun() causes full page reload - wait for it to complete.
        """
        expect(self.reset_thresholds_button).to_be_visible(timeout=5000)

        # Use JavaScript click to ensure the event triggers Streamlit's handler
        self.page.evaluate('''() => {
            const buttons = document.querySelectorAll('button');
            for (const btn of buttons) {
                if (btn.textContent.includes('Reset Thresholds')) {
                    btn.click();
                    return true;
                }
            }
            return false;
        }''')

        # st.rerun() causes full page reload - wait for it to complete
        self.page.wait_for_timeout(2000)
        self._wait_for_spinners_gone()
        self._wait_for_streamlit_ready()

    # =========================================================================
    # Actions - Expanders
    # =========================================================================

    def expand_about_section(self):
        """Expand the About Auto-Classification section."""
        expander = self.about_expander
        if expander.count() > 0:
            expander.click()
            self.page.wait_for_timeout(300)

    def expand_technical_details(self):
        """Expand the Technical Details section."""
        expander = self.technical_details_expander
        if expander.count() > 0:
            expander.click()
            self.page.wait_for_timeout(300)

    # =========================================================================
    # Assertions
    # =========================================================================

    def expect_page_loaded(self):
        """Assert that the Settings page has loaded."""
        expect(self.page_title).to_be_visible()

    def expect_classification_enabled(self):
        """Assert that classification is enabled."""
        expect(self.classification_enabled_info).to_be_visible()

    def expect_classification_disabled(self):
        """Assert that classification is disabled."""
        expect(self.classification_disabled_warning).to_be_visible()

    def expect_sliders_disabled(self):
        """Assert that threshold sliders are disabled.

        Note: Streamlit 1.53+ adds disabled attribute to the label when slider is disabled.
        """
        label = self.auto_apply_threshold_slider.locator('label[disabled]')
        expect(label).to_be_visible()

    def expect_sliders_enabled(self):
        """Assert that threshold sliders are enabled.

        Note: Streamlit 1.53+ removes disabled attribute from label when slider is enabled.
        """
        # Check that the label does NOT have the disabled attribute
        label = self.auto_apply_threshold_slider.locator('label:not([disabled])')
        expect(label).to_be_visible()

    def expect_label_exists(self, label_name: str):
        """Assert that a label exists."""
        expect(self.get_label_element(label_name)).to_be_visible()

    def expect_label_not_exists(self, label_name: str):
        """Assert that a label does not exist."""
        expect(self.get_label_element(label_name)).not_to_be_visible()

    def expect_label_count(self, count: int):
        """Assert the number of configured labels."""
        actual = self.get_label_count()
        assert actual == count, f"Expected {count} labels, got {actual}"

    def expect_auto_apply_threshold(self, value: int):
        """Assert the auto-apply threshold value."""
        actual = self.get_auto_apply_threshold()
        assert actual == value, f"Expected auto-apply threshold {value}, got {actual}"

    def expect_suggestion_threshold(self, value: int):
        """Assert the suggestion threshold value."""
        actual = self.get_suggestion_threshold()
        assert actual == value, f"Expected suggestion threshold {value}, got {actual}"

    def expect_success_message(self, text: str):
        """Assert that a success message is visible."""
        expect(self.get_success_message(text)).to_be_visible()
