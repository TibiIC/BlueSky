<script lang="ts">
	import favicon from '#lib/assets/favicon.svg';
	import type { LayoutProps } from './$types';

	let { children }: LayoutProps = $props();
</script>

<svelte:head>
	<link rel="icon" href={favicon} />
</svelte:head>

{@render children()}

<style>
	:global(:root) {
		color-scheme: dark;
		--panel-bg: rgba(12, 16, 26, 0.82);
		--panel-border: rgba(255, 255, 255, 0.09);
		--panel-shadow: 0 8px 30px rgba(0, 0, 0, 0.45);
		--text: #eef1f6;
		--text-dim: rgba(238, 241, 246, 0.7);
		--text-faint: rgba(238, 241, 246, 0.48);
	}
	:global(html, body) {
		margin: 0;
		height: 100%;
		background: #000;
		color: var(--text);
		font-family: Inter, system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif;
		-webkit-font-smoothing: antialiased;
		overflow: hidden;
	}
</style>
