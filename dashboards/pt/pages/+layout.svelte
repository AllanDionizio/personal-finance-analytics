<script>
	// Same as the English layout (dashboards/pages/+layout.svelte), in Portuguese
	import '@evidence-dev/tailwind/fonts.css';
	import '@fontsource-variable/geist';
	import '../app.css';
	import '../components/brand.css';
	import { EvidenceDefaultLayout } from '@evidence-dev/core-components';
	export let data;
</script>

<EvidenceDefaultLayout {data} title="Finanças da casa" homePageName="Resumo">
	<slot slot="content" />
</EvidenceDefaultLayout>
