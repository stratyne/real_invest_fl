import client from './client'
import type {
  FilterProfileResponse,
  FilterProfileCreateRequest,
  FilterProfileUpdateRequest,
  CloneProfileRequest,
} from '../types/api'

export async function listProfiles(countyFips: string): Promise<FilterProfileResponse[]> {
  const res = await client.get<FilterProfileResponse[]>(`/${countyFips}/profiles`)
  return res.data
}

export async function createProfile(
  countyFips: string,
  payload: FilterProfileCreateRequest
): Promise<FilterProfileResponse> {
  const res = await client.post<FilterProfileResponse>(`/${countyFips}/profiles`, payload)
  return res.data
}

export async function cloneProfile(
  countyFips: string,
  profileId: number,
  payload: CloneProfileRequest
): Promise<FilterProfileResponse> {
  const res = await client.post<FilterProfileResponse>(
    `/${countyFips}/profiles/${profileId}/clone`,
    payload
  )
  return res.data
}

export async function updateProfile(
  countyFips: string,
  profileId: number,
  payload: FilterProfileUpdateRequest
): Promise<FilterProfileResponse> {
  const res = await client.patch<FilterProfileResponse>(
    `/${countyFips}/profiles/${profileId}`,
    payload
  )
  return res.data
}

export async function deleteProfile(
  countyFips: string,
  profileId: number
): Promise<void> {
  await client.delete(`/${countyFips}/profiles/${profileId}`)
}
