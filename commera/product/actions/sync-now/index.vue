<script>
export const extension = {
  label: 'Sync to channel now',
  icon: 'refresh-cw',
  requires: 'Channel Listing',
  condition: 'commera_channel_sync.conditions.has_listings',
  method: 'commera_channel_sync.api.sync_product',
}
</script>
