'use strict';

// Static sample schedule rows. Stands in for a live SkyRoute Data Ltd feed so the
// fixture runs fully offline.
const SCHEDULES = [
  { flightNo: 'FL101', origin: 'SEA', destination: 'ORD', departs: '08:15', status: 'on-time' },
  { flightNo: 'FL118', origin: 'ORD', destination: 'JFK', departs: '11:40', status: 'on-time' },
  { flightNo: 'FL204', origin: 'JFK', destination: 'LHR', departs: '18:05', status: 'delayed' },
  { flightNo: 'FL330', origin: 'LHR', destination: 'FRA', departs: '06:50', status: 'on-time' },
  { flightNo: 'FL412', origin: 'FRA', destination: 'SEA', departs: '13:20', status: 'boarding' },
];

module.exports = { SCHEDULES };
