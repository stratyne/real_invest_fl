import client from './client'
import type {
  PaginatedPropertySearchResult,
  PropertyDetail,
  InlineSearchRequest,
} from '../types/api'

export async function searchProperties(
  filterProfileId: number,
  page = 1,
  pageSize = 25,
): Promise<PaginatedPropertySearchResult> {
  const res = await client.get<PaginatedPropertySearchResult>('/properties', {
    params: {
      filter_profile_id: filterProfileId,
      page,
      page_size: pageSize,
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
