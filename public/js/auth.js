/**
 * Supabase Auth Helper for Pudidi CMG Frontend
 * =============================================
 * Provides authentication functions for all protected pages
 * Uses cookie-based storage for reliable iOS/PWA support
 */

const AUTH_SUPABASE_URL = 'https://btyfbrclgmphcjgrvcgd.supabase.co';
const AUTH_SUPABASE_ANON_KEY = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImJ0eWZicmNsZ21waGNqZ3J2Y2dkIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NjEwMDk1MjksImV4cCI6MjA3NjU4NTUyOX0.JcZZLN_uxdXojor9Z8IaA1UhdThY_y7eWO265dHzsVo';

let authSupabase = null;
let authStateListenerSet = false;

/**
 * Initialize Supabase auth client
 * Sets up automatic token refresh handling with cookie-based storage
 */
function initAuth() {
    if (typeof window.supabase !== 'undefined' && !authSupabase) {
        // Use cookie storage if available (more reliable on iOS)
        const storageAdapter = (typeof CookieStorage !== 'undefined') ? CookieStorage : undefined;

        authSupabase = window.supabase.createClient(AUTH_SUPABASE_URL, AUTH_SUPABASE_ANON_KEY, {
            auth: {
                autoRefreshToken: true,      // Automatically refresh tokens before expiry
                persistSession: true,        // Persist session
                detectSessionInUrl: true,    // Handle OAuth redirects
                storage: storageAdapter,     // Use cookie storage for iOS reliability
                storageKey: 'sb-btyfbrclgmphcjgrvcgd-auth-token'
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
        // Clear all auth data (cookies + localStorage + sessionStorage)
        if (typeof clearAllAuthData === 'function') {
            clearAllAuthData();
        }
        localStorage.removeItem('supabase_session');
        redirectToLogin();
    } catch (error) {
        console.error('Logout error:', error);
        // Force clear and redirect even on error
        if (typeof clearAllAuthData === 'function') {
            clearAllAuthData();
        }
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
 * Shows the page content only after successful authentication
 */
async function requireAuth() {
    const session = await checkAuth();
    if (session) {
        console.log('User authenticated:', session.user.email);
        // Show page content after successful auth
        document.body.style.visibility = 'visible';
    }
    return session;
}

/**
 * Change user password
 * @param {string} newPassword - The new password
 * @returns {Promise<{success: boolean, error?: string}>}
 */
async function changePassword(newPassword) {
    const client = initAuth();
    if (!client) {
        return { success: false, error: 'Cliente de autenticacion no disponible' };
    }

    try {
        const { data, error } = await client.auth.updateUser({
            password: newPassword
        });

        if (error) {
            console.error('Password change error:', error);
            return { success: false, error: error.message };
        }

        return { success: true };
    } catch (err) {
        console.error('Password change exception:', err);
        return { success: false, error: 'Error al cambiar la contrasena' };
    }
}

/**
 * Get current user email
 * @returns {Promise<string|null>}
 */
async function getCurrentUserEmail() {
    const session = await getSession();
    return session?.user?.email || null;
}

/**
 * Show password change modal
 */
function showPasswordChangeModal() {
    // Remove existing modal if any
    const existing = document.getElementById('password-change-modal');
    if (existing) existing.remove();

    const modal = document.createElement('div');
    modal.id = 'password-change-modal';
    modal.className = 'fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50';
    modal.innerHTML = `
        <div class="bg-white rounded-xl shadow-2xl p-8 w-full max-w-md mx-4">
            <h2 class="text-2xl font-bold text-gray-800 mb-6">Cambiar Contrasena</h2>

            <div id="password-change-error" class="hidden bg-red-100 border border-red-400 text-red-700 px-4 py-3 rounded mb-4"></div>
            <div id="password-change-success" class="hidden bg-green-100 border border-green-400 text-green-700 px-4 py-3 rounded mb-4"></div>

            <div class="space-y-4">
                <div>
                    <label class="block text-sm font-medium text-gray-700 mb-2">Nueva Contrasena</label>
                    <input type="password" id="new-password"
                           class="w-full px-4 py-3 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                           placeholder="Minimo 8 caracteres">
                </div>
                <div>
                    <label class="block text-sm font-medium text-gray-700 mb-2">Confirmar Contrasena</label>
                    <input type="password" id="confirm-password"
                           class="w-full px-4 py-3 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                           placeholder="Repetir contrasena">
                </div>
            </div>

            <div class="flex gap-3 mt-6">
                <button onclick="closePasswordChangeModal()"
                        class="flex-1 bg-gray-200 hover:bg-gray-300 text-gray-800 font-semibold py-3 px-4 rounded-lg transition-colors">
                    Cancelar
                </button>
                <button onclick="submitPasswordChange()" id="submit-password-btn"
                        class="flex-1 bg-blue-600 hover:bg-blue-700 text-white font-semibold py-3 px-4 rounded-lg transition-colors">
                    Guardar
                </button>
            </div>
        </div>
    `;

    document.body.appendChild(modal);

    // Close on backdrop click
    modal.addEventListener('click', (e) => {
        if (e.target === modal) closePasswordChangeModal();
    });

    // Focus first input
    document.getElementById('new-password').focus();
}

/**
 * Close password change modal
 */
function closePasswordChangeModal() {
    const modal = document.getElementById('password-change-modal');
    if (modal) modal.remove();
}

/**
 * Submit password change
 */
async function submitPasswordChange() {
    const newPassword = document.getElementById('new-password').value;
    const confirmPassword = document.getElementById('confirm-password').value;
    const errorDiv = document.getElementById('password-change-error');
    const successDiv = document.getElementById('password-change-success');
    const submitBtn = document.getElementById('submit-password-btn');

    // Reset messages
    errorDiv.classList.add('hidden');
    successDiv.classList.add('hidden');

    // Validate
    if (!newPassword || newPassword.length < 8) {
        errorDiv.textContent = 'La contrasena debe tener al menos 8 caracteres';
        errorDiv.classList.remove('hidden');
        return;
    }

    if (newPassword !== confirmPassword) {
        errorDiv.textContent = 'Las contrasenas no coinciden';
        errorDiv.classList.remove('hidden');
        return;
    }

    // Disable button
    submitBtn.disabled = true;
    submitBtn.textContent = 'Guardando...';

    const result = await changePassword(newPassword);

    if (result.success) {
        successDiv.textContent = 'Contrasena actualizada exitosamente';
        successDiv.classList.remove('hidden');
        setTimeout(() => closePasswordChangeModal(), 1500);
    } else {
        errorDiv.textContent = result.error || 'Error al cambiar la contrasena';
        errorDiv.classList.remove('hidden');
        submitBtn.disabled = false;
        submitBtn.textContent = 'Guardar';
    }
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
        createLogoutButton,
        changePassword,
        getCurrentUserEmail,
        showPasswordChangeModal
    };
}
