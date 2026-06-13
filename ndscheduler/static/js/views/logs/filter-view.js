/**
 * logs-filter view.
 *
 * Extends BaseFilterView with logs-specific selectors and
 * collection method.
 *
 * @author wenbin@nextdoor.com
 * @refactor uses base-filter-view for shared filter lifecycle
 */

require.config({
  paths: {
    'jquery': 'vendor/jquery',
    'underscore': 'vendor/underscore',
    'backbone': 'vendor/backbone',
    'bootstrap': 'vendor/bootstrap',
    'moment': 'vendor/moment',

    'base-filter-view': 'views/base-filter-view'
  },

  shim: {
    'bootstrap': {
      deps: ['jquery']
    },
    'backbone': {
      deps: ['underscore', 'jquery'],
      exports: 'Backbone'
    }
  }
});

define(['backbone',
        'bootstrap',
        'moment',
        'base-filter-view'], function(backbone, bootstrap, moment, BaseFilterView) {
  'use strict';

  return BaseFilterView.extend({
    filterButtonId: 'logs-filter-button',
    timeRangeId: 'logs-filter-time-range',
    collectionMethod: 'getLogsByRange'
  });
});
