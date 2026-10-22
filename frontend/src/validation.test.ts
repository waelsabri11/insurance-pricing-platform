import { describe, expect, it } from 'vitest'
import { DEFAULT_FORM } from './App'
import { validate } from './validation'

describe('validate', () => {
  it('accepts the default form and converts to numbers', () => {
    const { errors, request } = validate(DEFAULT_FORM)
    expect(errors).toEqual({})
    expect(request).toMatchObject({ driver_age: 35, bonus_malus: 50, fuel_type: 'Regular' })
  })

  it.each([
    ['driver_age', '17'],
    ['driver_age', '35.5'],
    ['driver_age', ''],
    ['vehicle_power', '3'],
    ['bonus_malus', '40'],
    ['bonus_malus', '231'],
    ['population_density', '0'],
    ['population_density', 'abc'],
  ])('rejects %s = %j', (field, value) => {
    const { errors, request } = validate({ ...DEFAULT_FORM, [field]: value })
    expect(request).toBeNull()
    expect(errors[field as keyof typeof errors]).toBeTruthy()
  })

  it('accepts boundary values', () => {
    const { request } = validate({ ...DEFAULT_FORM, driver_age: '18', bonus_malus: '230', population_density: '27000' })
    expect(request).not.toBeNull()
  })

  it('has no protected-characteristic field', () => {
    expect(Object.keys(DEFAULT_FORM)).not.toContain('gender')
  })
})
