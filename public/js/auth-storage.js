/**
 * Cookie-based Storage Adapter for Supabase Auth
 * ===============================================
 * More reliable than localStorage on iOS Safari and PWAs
 * Cookies survive browser closes, ITP clearing, and PWA restarts
 */

const CookieStorage = {
    /**
     * Cookie configuration
     * - 365 days expiry for "remember me" functionality
     * - SameSite=Lax for security while allowing normal navigation
     * - Secure flag for HTTPS
     */
    COOKIE_EXPIRY_DAYS: 365,
    COOKIE_NAME: 'sb-auth-token',

    /**
     * Set a cookie with long expiry
     */
    setCookie(name, value, days) {
        const expires = new Date();
        expires.setTime(expires.getTime() + (days * 24 * 60 * 60 * 1000));

        // Use Secure flag only on HTTPS (production)
        const secure = window.location.protocol === 'https:' ? '; Secure' : '';

        document.cookie = `${name}=${encodeURIComponent(value)}; expires=${expires.toUTCString()}; path=/; SameSite=Lax${secure}`;
    },

    /**
     * Get a cookie value
     */
    getCookie(name) {
        const nameEQ = name + '=';
        const cookies = document.cookie.split(';');

        for (let cookie of cookies) {
            cookie = cookie.trim();
            if (cookie.indexOf(nameEQ) === 0) {
                return decodeURIComponent(cookie.substring(nameEQ.length));
            }
        }
        return null;
    },

    /**
     * Delete a cookie
     */
    deleteCookie(name) {
        document.cookie = `${name}=; expires=Thu, 01 Jan 1970 00:00:00 UTC; path=/; SameSite=Lax`;
    },

    /**
     * Supabase Storage Interface - getItem
     */
    getItem(key) {
        // Try cookie first (more reliable on iOS)
        const cookieValue = this.getCookie(this.COOKIE_NAME + '-' + key);
        if (cookieValue) {
            return cookieValue;
        }

        // Fallback to localStorage
        try {
            return localStorage.getItem(key);
        } catch (e) {
            console.warn('localStorage not available:', e);
            return null;
        }
    },

    /**
     * Supabase Storage Interface - setItem
     */
    setItem(key, value) {
        // Store in cookie (primary - survives iOS ITP)
        this.setCookie(this.COOKIE_NAME + '-' + key, value, this.COOKIE_EXPIRY_DAYS);

        // Also store in localStorage (backup)
        try {
            localStorage.setItem(key, value);
        } catch (e) {
            console.warn('localStorage setItem failed:', e);
        }
    },

    /**
     * Supabase Storage Interface - removeItem
     */
    removeItem(key) {
        // Remove from cookie
        this.deleteCookie(this.COOKIE_NAME + '-' + key);

        // Remove from localStorage
        try {
            localStorage.removeItem(key);
        } catch (e) {
            console.warn('localStorage removeItem failed:', e);
        }
    }
};

/**
 * Session-only storage (for when "Recuerdame" is unchecked)
 * Uses sessionStorage - clears when browser/tab closes
 */
const SessionOnlyStorage = {
    getItem(key) {
        try {
            return sessionStorage.getItem(key);
        } catch (e) {
            return null;
        }
    },

    setItem(key, value) {
        try {
            sessionStorage.setItem(key, value);
        } catch (e) {
            console.warn('sessionStorage setItem failed:', e);
        }
    },

    removeItem(key) {
        try {
            sessionStorage.removeItem(key);
        } catch (e) {
            console.warn('sessionStorage removeItem failed:', e);
        }
    }
};

/**
 * Get the appropriate storage based on "remember me" preference
 */
function getAuthStorage(rememberMe = true) {
    return rememberMe ? CookieStorage : SessionOnlyStorage;
}

/**
 * Check if user previously chose "remember me"
 */
function getRememberMePreference() {
    try {
        return localStorage.getItem('auth_remember_me') !== 'false';
    } catch (e) {
        return true; // Default to remember
    }
}

/**
 * Save "remember me" preference
 */
function setRememberMePreference(remember) {
    try {
        localStorage.setItem('auth_remember_me', remember ? 'true' : 'false');
    } catch (e) {
        // Ignore
    }
}

/**
 * Clear all auth data (for logout)
 */
function clearAllAuthData() {
    // Clear cookies
    CookieStorage.removeItem('sb-btyfbrclgmphcjgrvcgd-auth-token');

    // Clear localStorage
    try {
        const keysToRemove = [];
        for (let i = 0; i < localStorage.length; i++) {
            const key = localStorage.key(i);
            if (key && (key.includes('supabase') || key.includes('sb-'))) {
                keysToRemove.push(key);
            }
        }
        keysToRemove.forEach(key => localStorage.removeItem(key));
    } catch (e) {
        // Ignore
    }

    // Clear sessionStorage
    try {
        sessionStorage.clear();
    } catch (e) {
        // Ignore
    }
}
