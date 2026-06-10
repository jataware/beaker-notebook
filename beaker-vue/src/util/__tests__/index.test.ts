import { describe, it, expect } from 'vitest';
import { isErrorObject } from '../index';

describe('isErrorObject', () => {
  it('recognises an object carrying ename + evalue', () => {
    expect(isErrorObject({ ename: 'ValueError', evalue: 'bad input' })).toBe(true);
  });

  it('rejects objects missing the required keys', () => {
    expect(isErrorObject({ ename: 'ValueError' })).toBe(false);
    expect(isErrorObject({ message: 'nope' })).toBe(false);
  });
});
