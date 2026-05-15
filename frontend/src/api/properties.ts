import client from './client'
import type { PropertySearchResult, PropertyDetail } from '../types/api'
import type { FilterProfileCreateRequest } from '../types/api'

export async function searchProperties(
  filterProfileId: number
): Promise<PropertySearchResult[]> {
  const res = await client.get<PropertySearchResult[]>('/properties', {
    params: { filter_profile_id: filterProfileId },
  })
  return res.data
}

export async function searchPropertiesInline(
  payload: FilterProfileCreateRequest
): Promise<PropertySearchResult[]> {
  const res = await client.post<PropertySearchResult[]>('/properties/search', payload)
  return res.data
}

export async function getProperty(
  countyFips: string,
  parcelId: string
): Promise<PropertyDetail> {
  const res = await client.get<PropertyDetail>(`/${countyFips}/properties/${parcelId}`)
  return res.data
}
