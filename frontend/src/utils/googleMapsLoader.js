const GOOGLE_MAPS_KEY = (import.meta.env.VITE_GOOGLE_MAPS_API_KEY || '').trim();

let loadPromise = null;
let authFailed = false;

export function isGoogleMapsKeyConfigured() {
  return Boolean(GOOGLE_MAPS_KEY);
}

export function loadGoogleMapsApi() {
  if (!GOOGLE_MAPS_KEY) {
    return Promise.reject(new Error('GOOGLE_MAPS_KEY_MISSING'));
  }
  if (authFailed) {
    return Promise.reject(new Error('GOOGLE_MAPS_AUTH_FAILED'));
  }
  if (typeof window !== 'undefined' && window.google?.maps?.places) {
    return Promise.resolve(window.google.maps);
  }
  if (loadPromise) {
    return loadPromise;
  }

  loadPromise = new Promise((resolve, reject) => {
    const prevAuthFail = window.gm_authFailure;
    window.gm_authFailure = () => {
      authFailed = true;
      loadPromise = null;
      if (typeof prevAuthFail === 'function') prevAuthFail();
      reject(new Error('GOOGLE_MAPS_AUTH_FAILED'));
    };

    const existing = document.querySelector('script[data-slv-google-maps="1"]');
    if (existing) {
      existing.addEventListener('load', () => {
        if (!authFailed && window.google?.maps) resolve(window.google.maps);
        else reject(new Error('GOOGLE_MAPS_LOAD_FAILED'));
      });
      existing.addEventListener('error', () => {
        loadPromise = null;
        reject(new Error('GOOGLE_MAPS_SCRIPT_ERROR'));
      });
      return;
    }

    const cbName = '__slvGoogleMapsReady';
    window[cbName] = () => {
      delete window[cbName];
      if (!authFailed && window.google?.maps) {
        resolve(window.google.maps);
      } else {
        loadPromise = null;
        reject(new Error('GOOGLE_MAPS_LOAD_FAILED'));
      }
    };

    const script = document.createElement('script');
    script.dataset.slvGoogleMaps = '1';
    script.async = true;
    script.defer = true;
    script.src = `https://maps.googleapis.com/maps/api/js?key=${encodeURIComponent(GOOGLE_MAPS_KEY)}&libraries=places&v=weekly&callback=${cbName}`;
    script.onerror = () => {
      delete window[cbName];
      loadPromise = null;
      reject(new Error('GOOGLE_MAPS_SCRIPT_ERROR'));
    };
    document.head.appendChild(script);
  });

  return loadPromise;
}
