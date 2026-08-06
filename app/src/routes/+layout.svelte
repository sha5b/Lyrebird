<script lang="ts">
	import { onMount } from 'svelte';
	import '../app.css';
	import favicon from '$lib/assets/favicon.svg';

	let { children } = $props();

	/**
	 * Evict any service worker left on this origin by another project.
	 *
	 * **Lyrebird has no service worker**, so every registration on its origin belongs to
	 * something else. On `localhost` that happens constantly: a sibling app registers one at
	 * scope `/` on port 5173, and from then on every app that ever uses 5173 is served
	 * through a worker written for a different site. The visible symptom was Vite refusing a
	 * request for a file in a completely unrelated repository, forty times a second —
	 * `"/…/FE-Timer/src/service-worker.ts" is outside of Vite serving allow list` — because
	 * the dead worker keeps trying to fetch its own script.
	 *
	 * The noise is the harmless part. A worker controlling this page can answer `fetch` from
	 * its own Cache Storage, and the assets it would be answering for include
	 * `manifest.json` — the file whose `builtAt` stamp is the entire mechanism by which a
	 * running session notices the pipeline has rebuilt the galaxy. A stale cached manifest
	 * turns hot-reloading silently off, which is indistinguishable from the bug that was just
	 * fixed. So this is cleanup, not cosmetics.
	 *
	 * Their caches go too: an unregistered worker leaves its Cache Storage behind, and since
	 * Lyrebird owns none of it, anything there can only serve a stale response to somebody.
	 *
	 * One reload finishes the job, because a worker keeps controlling the page it is already
	 * attached to until navigation. The `sessionStorage` flag is what stops that from becoming
	 * a loop if the eviction ever fails to take.
	 */
	const EVICTED = 'lyrebird:evicted-foreign-sw';

	onMount(() => {
		if (!('serviceWorker' in navigator)) return;
		void (async () => {
			try {
				const registrations = await navigator.serviceWorker.getRegistrations();
				if (!registrations.length) return;
				const scripts = registrations.map(
					(r) => r.active?.scriptURL ?? r.installing?.scriptURL ?? r.scope
				);
				await Promise.all(registrations.map((r) => r.unregister()));
				if ('caches' in window) {
					const keys = await caches.keys();
					await Promise.all(keys.map((k) => caches.delete(k)));
				}
				console.warn(
					`Lyrebird: removed ${registrations.length} service worker(s) left on this origin ` +
						`by another app, and their caches. Lyrebird registers none of its own — a foreign ` +
						`worker can serve a stale manifest.json and quietly disable galaxy hot-reload. ` +
						`Evicted: ${scripts.join(', ')}`
				);
				// Still controlled: only a navigation detaches it, and until then it can keep
				// answering fetches from a cache that no longer exists.
				if (navigator.serviceWorker.controller && !sessionStorage.getItem(EVICTED)) {
					sessionStorage.setItem(EVICTED, '1');
					location.reload();
				}
			} catch (err) {
				// Never fatal: a browser that refuses this is a browser with a bit of extra noise
				// in its console, not a broken app.
				console.warn('Lyrebird: could not evict a foreign service worker', err);
			}
		})();
	});
</script>

<svelte:head>
	<link rel="icon" href={favicon} />
</svelte:head>

{@render children()}
