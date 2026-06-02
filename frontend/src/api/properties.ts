import client from './client'
import type {
  PaginatedPropertySearchResult,
  PropertyDetail,
  InlineSearchRequest,
  ParcelLookupResult,
} from '../types/api'

export async function searchProperties(
  filterProfileId: number,
  page = 1,
  pageSize = 25,
  sortField = 'deal_score',
  sortDirection: 'ASC' | 'DESC' = 'DESC',
): Promise<PaginatedPropertySearchResult> {
  const res = await client.get<PaginatedPropertySearchResult>('/properties', {
    params: {
      filter_profile_id: filterProfileId,
      page,
      page_size: pageSize,
      sort_field: sortField,
      sort_direction: sortDirection,
    },
  })
  return res.data
}

export async function searchPropertiesInline(
  payload: InlineSearchRequest,
): Promise<PaginatedPropertySearchResult> {
  const res = await client.post<PaginatedPropertySearchResult>(
    '/properties/search',
    payload,
  )
  return res.data
}

export async function getProperty(
  countyFips: string,
  parcelId: string,
): Promise<PropertyDetail> {
  const res = await client.get<PropertyDetail>(
    `/${countyFips}/properties/${parcelId}`,
  )
  return res.data
}

export async function lookupParcel(
  parcelId: string,
): Promise<ParcelLookupResult[]> {
  const res = await client.get<ParcelLookupResult[]>('/properties/lookup', {
    params: { parcel_id: parcelId },
  })
  return res.data
}
