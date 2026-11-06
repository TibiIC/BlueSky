<script lang="ts">
	const paths = {
		navigate: ['M5 3l6.5 17 2.6-7.4L21.5 10z'],
		freehand: ['M3 17c3-1 4.5-6 8-6 2.5 0 2 3 4.5 3s3.5-4 5.5-6', 'M3 21h18'],
		polygon: ['M12 3l8.5 6.2-3.2 10.3H6.7L3.5 9.2z'],
		undo: ['M9 14L4 9l5-5', 'M4 9h10.5a5.5 5.5 0 010 11H11'],
		trash: ['M3 6h18', 'M8 6V4h8v2', 'M19 6l-1 14H6L5 6', 'M10 11v5', 'M14 11v5'],
		download: ['M12 3v12', 'M7 10l5 5 5-5', 'M5 21h14'],
		cube: ['M12 2.5l8.5 4.8v9.4L12 21.5l-8.5-4.8V7.3z', 'M12 21.5V12', 'M20.5 7.3L12 12 3.5 7.3']
	} as const;

	let { name, size = 18 }: { name: keyof typeof paths; size?: number } = $props();
</script>

<svg
	width={size}
	height={size}
	viewBox="0 0 24 24"
	fill="none"
	stroke="currentColor"
	stroke-width="1.8"
	stroke-linecap="round"
	stroke-linejoin="round"
	aria-hidden="true"
>
	{#each paths[name] as d (d)}<path {d} />{/each}
</svg>
