import client from './client'
import type {
  FilterProfileResponse,
  FilterProfileCreateRequest,
  FilterProfileUpdateRequest,
  CloneProfileRequest,
} from '../types/api'

export async function listProfiles(): Promise<FilterProfileResponse[]> {
  const res = await client.get<FilterProfileResponse[]>('/profiles')
  return res.data
}

export async function createProfile(
  payload: FilterProfileCreateRequest
): Promise<FilterProfileResponse> {
  const res = await client.post<FilterProfileResponse>('/profiles', payload)
  return res.data
}

export async function cloneProfile(
  profileId: number,
  payload: CloneProfileRequest
): Promise<FilterProfileResponse> {
  const res = await client.post<FilterProfileResponse>(
    `/profiles/${profileId}/clone`,
    payload
  )
  return res.data
}

export async function updateProfile(
  profileId: number,
  payload: FilterProfileUpdateRequest
): Promise<FilterProfileResponse> {
  const res = await client.patch<FilterProfileResponse>(
    `/profiles/${profileId}`,
    payload
  )
  return res.data
}

export async function deleteProfile(profileId: number): Promise<void> {
  await client.delete(`/profiles/${profileId}`)
}

export async function toggleFavorite(
  profileId: number
): Promise<{ is_favorite: boolean }> {
  const res = await client.patch<{ is_favorite: boolean }>(
    `/profiles/${profileId}/favorite`
  )
  return res.data
}
