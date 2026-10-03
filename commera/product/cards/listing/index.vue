<script>
export const extension = { label: 'Channel listing', requires: 'Channel Listing' }
</script>

<script setup>
import { computed, watch } from 'vue'
import { Skeleton, dayjs } from 'frappe-ui'
import { StatusBadge, money, useCard, useExtension, useMethodRead, usePolling } from '@commera/admin'
import { SYNC_STATUS_KEYS } from '../../../shared/status'

const { record } = useExtension()
const card = useCard()

const listingsRequest = useMethodRead('commera_channel_sync.api.get_product_listings', {
  params: () => ({ item: record.value.name }),
})

const listings = computed(() => listingsRequest.data ?? [])

usePolling(listingsRequest, {
  every: 5000,
  while: () => listings.value.some((listing) => listing.sync_status === 'Pending'),
})

// Hidden until the listings arrive, so a product that isn't on the channel never flashes an empty card.
card.hide()
watch(
  () => listingsRequest.data,
  (rows) => card.setHidden(!rows?.length),
)
</script>

<template>
  <Skeleton v-if="listingsRequest.loading && !listingsRequest.data" class="h-16 w-full rounded-4" />
  <div v-else class="divide-y divide-outline-gray-1">
    <div
      v-for="listing in listings"
      :key="listing.name"
      class="flex items-center justify-between gap-3 py-2 first:pt-0 last:pb-0"
    >
      <div class="min-w-0">
        <p class="truncate text-base text-ink-gray-8">{{ listing.item_code }}</p>
        <p class="truncate text-sm text-ink-gray-5 tabular-nums">
          {{ money(listing.price) }} · {{ listing.available_qty }} in stock ·
          {{ listing.last_synced_at ? `synced ${dayjs(listing.last_synced_at).fromNow()}` : 'never synced' }}
        </p>
      </div>
      <StatusBadge :status="SYNC_STATUS_KEYS[listing.sync_status] ?? 'draft'" :label="listing.sync_status" />
    </div>
  </div>
</template>
