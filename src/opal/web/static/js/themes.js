/**
 * OPAL Theme System - Catppuccin Themes
 * https://github.com/catppuccin/catppuccin
 */

const THEMES = {
    mocha: {
        name: 'MOCHA',
        colors: {
            '--bg-primary': '#1e1e2e',
            '--bg-secondary': '#181825',
            '--bg-tertiary': '#313244',
            '--border-color': '#45475a',
            '--border-light': '#585b70',
            '--text-primary': '#cdd6f4',
            '--text-secondary': '#bac2de',
            '--text-muted': '#a6adc8',
            '--accent-blue': '#74c7ec',
            '--accent-green': '#a6e3a1',
            '--accent-yellow': '#f9e2af',
            '--accent-red': '#f38ba8',
            '--accent-orange': '#fab387'
        }
    },
    latte: {
        name: 'LATTE',
        colors: {
            '--bg-primary': '#eff1f5',
            '--bg-secondary': '#e6e9ef',
            '--bg-tertiary': '#ccd0da',
            '--border-color': '#bcc0cc',
            '--border-light': '#acb0be',
            '--text-primary': '#4c4f69',
            '--text-secondary': '#5c5f77',
            '--text-muted': '#6c6f85',
            '--accent-blue': '#209fb5',
            '--accent-green': '#40a02b',
            '--accent-yellow': '#df8e1d',
            '--accent-red': '#d20f39',
            '--accent-orange': '#fe640b'
        }
    }
};

const DEFAULT_THEME = 'mocha';
const STORAGE_KEY = 'opal_theme';

/**
 * Apply a theme by setting CSS variables on the document root
 */
function applyTheme(themeName) {
    const theme = THEMES[themeName];
    if (!theme) return;

    const root = document.documentElement;
    Object.entries(theme.colors).forEach(([property, value]) => {
        root.style.setProperty(property, value);
    });
}

/**
 * Set theme and persist to localStorage
 */
function setTheme(themeName) {
    applyTheme(themeName);
    localStorage.setItem(STORAGE_KEY, themeName);
}

/**
 * Get current theme from localStorage or return default
 */
function getTheme() {
    return localStorage.getItem(STORAGE_KEY) || DEFAULT_THEME;
}

/**
 * Initialize theme system on page load
 */
function initTheme() {
    const currentTheme = getTheme();
    applyTheme(currentTheme);

    // Update select if it exists
    const themeSelect = document.getElementById('theme-select');
    if (themeSelect) {
        themeSelect.value = currentTheme;
    }
}

/**
 * Toggle between available themes
 */
function toggleTheme() {
    const currentTheme = getTheme();
    const newTheme = currentTheme === 'mocha' ? 'latte' : 'mocha';
    setTheme(newTheme);

    // Update select if it exists
    const themeSelect = document.getElementById('theme-select');
    if (themeSelect) {
        themeSelect.value = newTheme;
    }
}

// Export API for global access
window.OPAL_THEMES = {
    setTheme,
    getTheme,
    initTheme,
    toggleTheme,
    THEMES
};
