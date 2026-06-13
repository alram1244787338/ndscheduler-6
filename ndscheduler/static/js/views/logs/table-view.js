/**
 * logs-table view.
 *
 * Extends BaseTableView with logs-specific row building and
 * collection refresh behaviour.
 *
 * @author wenbin@nextdoor.com
 * @refactor uses base-table-view for shared DataTable lifecycle
 */

require.config({
  paths: {
    'jquery': 'vendor/jquery',
    'underscore': 'vendor/underscore',
    'backbone': 'vendor/backbone',
    'bootstrap': 'vendor/bootstrap',
    'datatables': 'vendor/jquery.dataTables',

    'utils': 'utils',
    'base-table-view': 'views/base-table-view'
  },

  shim: {
    'bootstrap': {
      deps: ['jquery']
    },

    'backbone': {
      deps: ['underscore', 'jquery'],
      exports: 'Backbone'
    },

    'datatables': {
      deps: ['jquery'],
      exports: '$.fn.dataTable'
    }
  }
});

define(['utils',
        'base-table-view',
        'backbone',
        'bootstrap',
        'datatables'], function(utils, BaseTableView) {
  'use strict';

  return BaseTableView.extend({

    tableId: 'logs-table',
    spinnerId: 'logs-spinner',

    /**
     * DataTable options -- sorted by time descending.
     */
    dataTableOptions: function() {
      return { 'order': [[3, 'desc']] };
    },

    /**
     * Re-fetch the logs collection (used by the base reset / refresh flow).
     */
    refreshCollection: function() {
      this.collection.getLogs();
    },

    /**
     * Build row data array from the logs collection.
     */
    buildRows: function() {
      var logs = this.collection.logs;
      var data = [];

      _.each(logs, function(log) {
        var logObj = log.toJSON();
        data.push([
          log.getJobNameHTMLString(),
          log.getEventHTMLString(),
          logObj.user,
          log.getEventTimeString(),
          log.getDescriptionHTMLString()
        ]);
      });

      return data;
    }
  });
});
