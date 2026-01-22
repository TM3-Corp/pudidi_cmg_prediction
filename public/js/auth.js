/**
 * Supabase Auth Helper for Pudidi CMG Frontend
 * =============================================
 * Provides authentication functions for all protected pages
 */

const AUTH_SUPABASE_URL = 'https://btyfbrclgmphcjgrvcgd.supabase.co';
const AUTH_SUPABASE_ANON_KEY = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImJ0eWZicmNsZ21waGNqZ3J2Y2dkIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NjEwMDk1MjksImV4cCI6MjA3NjU4NTUyOX0.WQK2xJMa6YWUABsXq2MQwJGpOQHt5GfZJ5pLe7MZIi8';

let authSupabase = null;
let authStateListenerSet = false;

/**
 * Initialize Supabase auth client
 * Sets up automatic token refresh handling
 */
function initAuth() {
    if (typeof window.supabase !== 'undefined' && !authSupabase) {
        authSupabase = window.supabase.createClient(AUTH_SUPABASE_URL, AUTH_SUPABASE_ANON_KEY, {
            auth: {
                autoRefreshToken: true,      // Automatically refresh tokens before expiry
                persistSession: true,        // Persist session in localStorage
                detectSessionInUrl: true     // Handle OAuth redirects
            }
        });

        // Set up auth state change listener (only once)
        if (!authStateListenerSet) {
            authSupabase.auth.onAuthStateChange((event, session) => {
                console.log('Auth state changed:', event);

                if (event === 'TOKEN_REFRESHED') {
                    console.log('Access token refreshed automatically');
                }

                if (event === 'SIGNED_OUT') {
                    // User was signed out (token expired and couldn't refresh, or manual logout)
                    if (!window.location.pathname.includes('login.html')) {
                        redirectToLogin();
                    }
                }
            });
            authStateListenerSet = true;
        }
    }
    return authSupabase;
}

/**
 * Check if user is authenticated
 * Redirects to login page if not authenticated
 * @returns {Promise<Object|null>} Session object or null
 */
async function checkAuth() {
    const client = initAuth();
    if (!client) {
        console.warn('Supabase client not available - auth check skipped');
        return null;
    }

    try {
        const { data: { session }, error } = await client.auth.getSession();

        if (error) {
            console.error('Auth check error:', error);
            redirectToLogin();
            return null;
        }

        if (!session) {
            redirectToLogin();
            return null;
        }

        return session;
    } catch (error) {
        console.error('Auth check failed:', error);
        redirectToLogin();
        return null;
    }
}

/**
 * Get current session without redirecting
 * @returns {Promise<Object|null>} Session object or null
 */
async function getSession() {
    const client = initAuth();
    if (!client) return null;

    try {
        const { data: { session } } = await client.auth.getSession();
        return session;
    } catch (error) {
        console.error('Get session error:', error);
        return null;
    }
}

/**
 * Get access token for API requests
 * @returns {Promise<string|null>} JWT access token or null
 */
async function getAccessToken() {
    const session = await getSession();
    return session?.access_token || null;
}

/**
 * Logout current user
 * @returns {Promise<void>}
 */
async function logout() {
    const client = initAuth();
    if (!client) {
        redirectToLogin();
        return;
    }

    try {
        await client.auth.signOut();
        localStorage.removeItem('supabase_session');
        redirectToLogin();
    } catch (error) {
        console.error('Logout error:', error);
        // Force redirect even on error
        redirectToLogin();
    }
}

/**
 * Redirect to login page
 */
function redirectToLogin() {
    if (!window.location.pathname.includes('login.html')) {
        window.location.href = '/login.html';
    }
}

/**
 * Add auth header to fetch requests
 * @param {Object} options - Fetch options
 * @returns {Promise<Object>} Options with auth header
 */
async function addAuthHeader(options = {}) {
    const token = await getAccessToken();
    if (token) {
        options.headers = options.headers || {};
        options.headers['Authorization'] = `Bearer ${token}`;
    }
    return options;
}

/**
 * Authenticated fetch wrapper
 * @param {string} url - URL to fetch
 * @param {Object} options - Fetch options
 * @returns {Promise<Response>}
 */
async function authFetch(url, options = {}) {
    const authOptions = await addAuthHeader(options);
    return fetch(url, authOptions);
}

/**
 * Create logout button HTML
 * @returns {string} HTML for logout button
 */
function createLogoutButton() {
    return `
        <button onclick="logout()"
                class="bg-red-600 hover:bg-red-700 text-white px-4 py-2 rounded-lg transition-colors flex items-center gap-2">
            <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                      d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1"></path>
            </svg>
            <span>Salir</span>
        </button>
    `;
}

/**
 * Initialize auth check on page load
 * Call this at the top of DOMContentLoaded in protected pages
 */
async function requireAuth() {
    const session = await checkAuth();
    if (session) {
        console.log('User authenticated:', session.user.email);
    }
    return session;
}

// Export for use in other scripts
if (typeof module !== 'undefined' && module.exports) {
    module.exports = {
        initAuth,
        checkAuth,
        getSession,
        getAccessToken,
        logout,
        addAuthHeader,
        authFetch,
        requireAuth,
        createLogoutButton
    };
}
