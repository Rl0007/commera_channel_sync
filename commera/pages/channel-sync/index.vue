<script>
export const extension = { label: 'Channel sync', icon: 'refresh-cw', requires: 'Channel Listing' }
</script>

<script setup>
import { computed, ref, watch } from 'vue'
import { Alert, Skeleton, TabButtons, dayjs } from 'frappe-ui'
import { List, ListCell, ListHeader, ListHeaderCell, ListRow, ListRows } from 'frappe-ui/list'
import {
  EmptyState,
  ListPagination,
  ListSkeleton,
  StatusBadge,
  money,
  useMethodRead,
  usePolling,
} from '@commera/admin'
import { SYNC_STATUS_KEYS } from '../../shared/status'

const TABS = [
  { label: 'All', value: 'all' },
  { label: 'Synced', value: 'Synced' },
  { label: 'Pending', value: 'Pending' },
  { label: 'Failed', value: 'Failed' },
]
const ROW_HEIGHT = 60

const tab = ref('all')
const page = ref(1)
const pageSize = ref(20)

const listingsRequest = useMethodRead('commera_channel_sync.api.get_listings', {
  params: () => ({
    sync_status: tab.value === 'all' ? undefined : tab.value,
    start: (page.value - 1) * pageSize.value,
    page_length: pageSize.value,
  }),
  refetch: true,
})

watch(tab, () => (page.value = 1))

const listings = computed(() => listingsRequest.data)
const rows = computed(() => listings.value?.rows ?? [])
const total = computed(() => listings.value?.total ?? 0)
const counts = computed(() => listings.value?.counts ?? {})

usePolling(listingsRequest, { every: 5000, while: () => counts.value.Pending > 0 })

const stats = computed(() => [
  { label: 'Synced', value: counts.value.Synced ?? 0 },
  { label: 'Pending', value: counts.value.Pending ?? 0 },
  { label: 'Failed', value: counts.value.Failed ?? 0 },
])

const skeletonColumns = window.matchMedia('(max-width: 639.98px)').matches ? 2 : 5
</script>

<template>
  <Alert
    v-if="listings?.channel_down"
    class="mb-5"
    theme="red"
    title="Channel is down"
    description="Listings stay pending and retry on their own once the channel answers again."
  />

  <div class="grid grid-cols-3 divide-x divide-outline-gray-2 rounded-5 border border-outline-gray-1">
    <div v-for="stat in stats" :key="stat.label" class="px-4 py-3.5">
      <Skeleton v-if="listingsRequest.loading && !listings" class="h-12 w-full rounded-4" />
      <template v-else>
        <p class="text-sm text-ink-gray-5">{{ stat.label }}</p>
        <p class="mt-1 text-2xl text-ink-gray-9 tabular-nums">{{ stat.value }}</p>
      </template>
    </div>
  </div>

  <div class="mt-5 flex flex-wrap items-center gap-2">
    <TabButtons v-model="tab" size="sm" :options="TABS" />
  </div>

  <div class="mt-3 overflow-x-auto">
    <List
      class="max-sm:[--list-columns:minmax(0,1fr)_auto] sm:min-w-[44rem]"
      :row-height="ROW_HEIGHT"
      :columns="['1fr', '7rem', '5rem', '9rem', '7rem']"
    >
      <ListHeader>
        <ListHeaderCell>Listing</ListHeaderCell>
        <ListHeaderCell class="justify-end max-sm:hidden">Price</ListHeaderCell>
        <ListHeaderCell class="justify-end max-sm:hidden">Qty</ListHeaderCell>
        <ListHeaderCell class="pl-6 max-sm:hidden">Last synced</ListHeaderCell>
        <ListHeaderCell>Status</ListHeaderCell>
      </ListHeader>

      <ListSkeleton v-if="listingsRequest.loading && !rows.length" :columns="skeletonColumns" />

      <ListRows v-else :items="rows" row-key="name" v-slot="{ item }">
        <ListRow :value="item.name">
          <ListCell>
            <div class="min-w-0">
              <p class="truncate text-base text-ink-gray-8">{{ item.title || item.item_code }}</p>
              <p class="truncate text-sm text-ink-gray-4">{{ item.item_code }}</p>
            </div>
          </ListCell>
          <ListCell class="max-sm:hidden">
            <span class="w-full text-right text-base text-ink-gray-7 tabular-nums">{{ money(item.price) }}</span>
          </ListCell>
          <ListCell class="max-sm:hidden">
            <span class="w-full text-right text-base text-ink-gray-7 tabular-nums">{{ item.available_qty }}</span>
          </ListCell>
          <ListCell class="pl-6 max-sm:hidden">
            <span class="text-sm text-ink-gray-5">
              {{ item.last_synced_at ? dayjs(item.last_synced_at).fromNow() : 'Never' }}
            </span>
          </ListCell>
          <ListCell>
            <StatusBadge :status="SYNC_STATUS_KEYS[item.sync_status] ?? 'draft'" :label="item.sync_status" />
          </ListCell>
        </ListRow>
      </ListRows>
    </List>
  </div>

  <ListPagination v-if="total" v-model:page="page" v-model:page-size="pageSize" :total="total" />

  <EmptyState
    v-if="!listingsRequest.loading && !rows.length"
    icon="lucide-refresh-cw"
    title="Nothing listed on the channel yet"
    description="A product lands here the first time it changes in your store, and stays in step after that."
    :filtered="tab !== 'all'"
    filtered-title="No listings with this status"
    filtered-description="Pick another tab to see the rest."
  />
</template>
