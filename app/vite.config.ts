import adapter from '@sveltejs/adapter-static';
import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig } from 'vite';
import { birdyPipeline } from './vite-plugin-pipeline';

export default defineConfig({
	plugins: [
		// Dev only, and never required: it starts `birdy-pipeline serve` so the Learn tab
		// has its backend without a second terminal. Nothing else in the app talks to it.
		birdyPipeline(),
		sveltekit({
			compilerOptions: {
				// Force runes mode for the project, except for libraries. Can be removed in svelte 6.
				runes: ({ filename }) =>
					filename.split(/[/\\]/).includes('node_modules') ? undefined : true
			},

			// Lyrebird v1 is fully client-side: precomputed galaxy assets, client-side features,
			// client-side synthesis. Switch to adapter-node when the WebSocket "bird rooms" or a
			// server-side Perch endpoint arrive (docs/06-architecture.md §6.1).
			adapter: adapter({ fallback: '404.html' })
		})
	]
});
