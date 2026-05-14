import client from './client'
import type { PropertySearchResult, PropertyDetail } from '../types/api'

export async function searchProperties(
  countyFips: string,
  filterProfileId: number
): Promise<PropertySearchResult[]> {
  const res = await client.get<PropertySearchResult[]>(`/${countyFips}/properties`, {
    params: { filter_profile_id: filterProfileId },
  })
  return res.data
}

export async function getProperty(
  countyFips: string,
  parcelId: string
): Promise<PropertyDetail> {
  const res = await client.get<PropertyDetail>(`/${countyFips}/properties/${parcelId}`)
  return res.data
}
