<script>
	/** A query with one row from canecon.series */
	export let data;
	/** Extra sentence, e.g. how a derived number was computed */
	export let note = '';
	$: s = data && data.length ? data[0] : undefined;
</script>

{#if s}
	<p class="text-sm opacity-80 mt-1 mb-8">
		<b>{s.label}.</b>
		{s.definition}
		{note}
		Source: {s.source_name},
		<a class="underline" href={s.source_url} target="_blank" rel="noreferrer">{s.source_code}</a>.
	</p>
{/if}
