<script>
	// Same as Evidence's default layout, plus the font and the brand styles
	import '@evidence-dev/tailwind/fonts.css';
	import '@fontsource-variable/geist';
	import '../app.css';
	import '../components/brand.css';
	import { EvidenceDefaultLayout } from '@evidence-dev/core-components';
	export let data;
</script>

<EvidenceDefaultLayout
	{data}
	title="Household Finance"
	homePageName="Summary"
	githubRepo="https://github.com/AllanDionizio/personal-finance-analytics"
>
	<slot slot="content" />
</EvidenceDefaultLayout>
