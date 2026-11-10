import { defineCatalog } from '@json-render/core'
import { schema } from '@json-render/react/schema'
import { shadcnComponentDefinitions as d } from '@json-render/shadcn/catalog'
import { customDefinitions } from './custom'

// The components a page spec (hand-written or model-generated) may use.
export const components = ['Card', 'Stack', 'Grid', 'Separator', 'Heading', 'Text', 'Badge', 'Alert', 'Table', 'Progress', 'Skeleton', 'Spinner', 'Button', 'Link', 'Input', 'Textarea', 'Checkbox', 'Switch', 'Tabs'] as const

export const catalog = defineCatalog(schema, {
  components: {
    ...(Object.fromEntries(components.map((name) => [name, d[name]])) as { [K in (typeof components)[number]]: (typeof d)[K] }),
    ...customDefinitions,
  },
  actions: {},
})
