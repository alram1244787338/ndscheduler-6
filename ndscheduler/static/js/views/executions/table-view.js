/**
 * executions-table view.
 *
 * Extends BaseTableView with executions-specific row building,
 * result modal popup, and column configuration.
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
    'base-table-view': 'views/base-table-view',
    'text': 'vendor/text',
    'execution-result': 'templates/execution-result.html'
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
        'text!execution-result',
        'backbone',
        'bootstrap',
        'datatables'], function(utils, BaseTableView, ExecutionResultHtml) {
  'use strict';

  return BaseTableView.extend({

    tableId: 'executions-table',
    spinnerId: 'executions-spinner',

    /**
     * DataTable options -- sorted by last updated time descending,
     * result column is not orderable.
     */
    dataTableOptions: function() {
      return {
        'order': [[3, 'desc']],
        'columnDefs': [
          { 'orderable': false, 'className': 'table-result-column', 'targets': 5 }
        ]
      };
    },

    /**
     * Append the result modal template and wire up show-result button
     * handlers on each DataTable draw event.
     */
    _bindDOMEvents: function() {
      $('body').append(ExecutionResultHtml);

      var $table = $('#executions-table');

      // Remove any previous draw.dt handler to avoid duplicates
      $table.off('draw.dt').on('draw.dt', function() {
        var buttons = $('[data-action=show-result]');
        _.each(buttons, function(btn) {
          $(btn).off('click').on('click', function(e) {
            e.preventDefault();
            $('#result-box').text(decodeURI($(btn).data('content')));
            $('#execution-result-modal').modal();
          });

          // If there is a query parameter result, display the result.
          if (!_.isUndefined(utils.getParameterByName('result'))) {
            if (typeof executions !== 'undefined' && executions[0]) {
              $('#result-box').text(executions[0].get('result'));
              $('#execution-result-modal').modal();
            }
          }
        });
      });
    },

    /**
     * Build row data array from the executions collection.
     */
    buildRows: function() {
      var executions = this.collection.executions;
      var data = [];

      _.each(executions, function(execution) {
        data.push([
          execution.getNameHTMLString(),
          execution.getStatusHTMLString(),
          execution.getScheduledAtString(),
          execution.getFinishedAtString(),
          execution.getDescription(),
          execution.getResult()
        ]);
      });

      return data;
    }
  });
});
