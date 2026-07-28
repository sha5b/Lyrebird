import adapter from '@sveltejs/adapter-static';
import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig } from 'vite';

export default defineConfig({
	plugins: [
		sveltekit({
			compilerOptions: {
				// Force runes mode for the project, except for libraries. Can be removed in svelte 6.
				runes: ({ filename }) =>
					filename.split(/[/\\]/).includes('node_modules') ? undefined : true
			},

			// Birdy v1 is fully client-side: precomputed galaxy assets, client-side features,
			// client-side synthesis. Switch to adapter-node when the WebSocket "bird rooms" or a
			// server-side Perch endpoint arrive (docs/06-architecture.md §6.1).
			adapter: adapter({ fallback: '404.html' })
		})
	]
});
