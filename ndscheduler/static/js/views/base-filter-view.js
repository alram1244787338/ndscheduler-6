/**
 * Base filter view for time-range based collection filtering.
 *
 * Provides:
 *  - Click handler on a configurable filter button
 *  - Time range calculation using moment.js
 *  - Safe (off-then-on) event binding to prevent duplicate handlers
 *
 * Subclasses override:
 *  - filterButtonId   : DOM id of the filter / refresh button
 *  - timeRangeId      : DOM id of the <select> with time range values
 *  - collectionMethod : name of the collection method to call with (start, end)
 *
 * @refactor extracted from executions/filter-view and logs/filter-view
 */

require.config({
  paths: {
    'jquery': 'vendor/jquery',
    'underscore': 'vendor/underscore',
    'backbone': 'vendor/backbone',
    'bootstrap': 'vendor/bootstrap',
    'moment': 'vendor/moment'
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

define(['backbone', 'bootstrap', 'moment'], function(backbone, bootstrap, moment) {
  'use strict';

  return Backbone.View.extend({

    /** DOM id of the filter button -- must be set by subclass. */
    filterButtonId: null,

    /** DOM id of the time-range <select> -- must be set by subclass. */
    timeRangeId: null,

    /**
     * Name of the collection method to invoke with (start, end) ISO strings.
     * Must be set by subclass (e.g. 'getExecutionsByRange', 'getLogsByRange').
     */
    collectionMethod: null,

    initialize: function() {
      this._bindFilterEvent();
    },

    /**
     * Bind the click handler using off-then-on to prevent duplicate bindings.
     */
    _bindFilterEvent: function() {
      var $button = $('#' + this.filterButtonId);
      $button.off('click').on('click', _.bind(this.filterTable, this));
    },

    /**
     * Click handler -- reads the selected range, computes start/end, and
     * calls the configured collection method.
     *
     * @param {Event} e click event
     */
    filterTable: function(e) {
      e.preventDefault();

      var range = parseInt($('#' + this.timeRangeId).val(), 10);
      var end = moment();
      var start = moment().subtract(range, 'second');
      this.collection[this.collectionMethod](
        start.toISOString(),
        end.toISOString()
      );
    }
  });
});
